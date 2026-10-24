/*
 * audio_control - Nios II firmware for the guitar multi-effect (DE1-SoC)
 *
 *  - initialises the audio codec over I2C (bit-banged on two PIOs)
 *  - receives 3-byte command frames from the PC GUI on the UART (9600 8N1)
 *    and writes them to the effect registers / codec
 *
 * Frame format (see docs/register_map.md):
 *   [cmd][hi][lo]   cmd 0x00..0x0E : effect register cmd = (hi << 8) | lo
 *                   cmd 0xCD       : codec register write, hi = (reg << 1) | d8, lo = d7..d0
 *                   cmd 0xEC       : re-run the default codec initialisation
 */

#include <stdio.h>
#include <unistd.h>
#include "system.h"
#include "alt_types.h"
#include "sys/alt_irq.h"
#include "altera_avalon_uart_regs.h"

#include "my_includes.h"
#include "I2C.h"

/* ---- effect registers (RegistersControl, 16-bit, offset = reg * 2) -------- */
#define REG_EFFECTS_ENABLE   0x00
#define REG_OD_DRIVE         0x01
#define REG_OD_GAIN          0x02
#define REG_TREM_WAVE        0x03
#define REG_TREM_DEPTH       0x04
#define REG_ECHO_TIME        0x05
#define REG_ECHO_REPEAT      0x06
#define REG_ECHO_LEVEL       0x07
#define REG_DIST_MIX         0x08
#define REG_DIST_TYPE        0x09
#define REG_CHORUS_LEVEL     0x0A
#define REG_CHORUS_DEPTH     0x0B
#define REG_CHORUS_RATE      0x0C
#define REG_REVERB_MIX       0x0D
#define REG_REVERB_TYPE      0x0E
#define REG_LAST             REG_REVERB_TYPE

#define Effect_Update(REG, DATA) \
  IOWR_16DIRECT(REGISTERSCONTROL_0_BASE, (REG) * 2, (DATA))

/* ---- UART commands --------------------------------------------------------- */
#define CMD_CODEC_UPDATE     0xCD
#define CMD_CODEC_PRESET     0xEC

#define codec_addr           0x34      /* WM8731 / SSM2603 I2C address */

#define UART_BAUD_RATE       9600
#define FRAME_LEN            3
/* A partially received frame is discarded if no byte arrives for this long,
 * so the parser re-synchronises after a lost byte (the PC sends the 3 bytes
 * of a frame a few ms apart). */
#define FRAME_TIMEOUT_MS     50

/* ---- state shared between the UART ISR and main() -------------------------- */
static volatile alt_u8  rx_frame[FRAME_LEN];   /* last complete frame        */
static volatile alt_u8  frame_ready  = 0;      /* rx_frame holds a new frame */
static volatile alt_u8  rx_index     = 0;      /* bytes of the frame so far  */
static volatile alt_u8  rx_activity  = 0;      /* set by ISR on every byte   */
static volatile alt_u32 rx_overruns  = 0;      /* frames dropped / UART errors */

static alt_u8 isr_buf[FRAME_LEN];

static int is_valid_command(alt_u8 cmd)
{
    return cmd <= REG_LAST || cmd == CMD_CODEC_UPDATE || cmd == CMD_CODEC_PRESET;
}

static void handle_UART_interrupts(void* context)
{
    alt_u32 status = IORD_ALTERA_AVALON_UART_STATUS(UART_BASE);
    alt_u8  byte   = IORD_ALTERA_AVALON_UART_RXDATA(UART_BASE);

    (void)context;
    IOWR_ALTERA_AVALON_UART_STATUS(UART_BASE, 0);   /* clear error flags */
    rx_activity = 1;

    if (status & (ALTERA_AVALON_UART_STATUS_FE_MSK |
                  ALTERA_AVALON_UART_STATUS_PE_MSK |
                  ALTERA_AVALON_UART_STATUS_ROE_MSK)) {
        rx_index = 0;                               /* corrupted: start over */
        rx_overruns++;
        return;
    }

    if (rx_index == 0 && !is_valid_command(byte))
        return;                                     /* not a frame start: skip */

    isr_buf[rx_index++] = byte;

    if (rx_index == FRAME_LEN) {
        rx_index = 0;
        if (frame_ready) {
            rx_overruns++;                          /* main() too slow: drop */
        } else {
            rx_frame[0] = isr_buf[0];
            rx_frame[1] = isr_buf[1];
            rx_frame[2] = isr_buf[2];
            frame_ready = 1;
        }
    }
}

static void InitUart(unsigned int BaudRate)
{
    /* Altera UART: baud = clk / (divisor + 1) */
    unsigned int divisor = (UART_FREQ + BaudRate / 2) / BaudRate - 1;
    IOWR_ALTERA_AVALON_UART_DIVISOR(UART_BASE, divisor);
    IOWR_ALTERA_AVALON_UART_CONTROL(UART_BASE, ALTERA_AVALON_UART_CONTROL_RRDY_MSK);
}

static void update_codec_regs(alt_u8 address, alt_u8 data)
{
    I2C_Write(I2C_SCL_BASE, I2C_SDA_BASE, codec_addr, address, data);
}

static void init_codec(void)
{
    update_codec_regs(0x1E, 0x00); // R15 Software Reset
    update_codec_regs(0x12, 0x00); // R9  Active = 0
    update_codec_regs(0x00, 0x1A); // R0  Left  line-in volume
    update_codec_regs(0x02, 0x1A); // R1  Right line-in volume
    update_codec_regs(0x04, 0x7A); // R2  Left  headphone volume
    update_codec_regs(0x06, 0x7A); // R3  Right headphone volume
    update_codec_regs(0x08, 0x10); // R4  Analog path: DAC select, line input
    update_codec_regs(0x0A, 0x00); // R5  Digital path
    update_codec_regs(0x0C, 0x00); // R6  Power down control: all on
    update_codec_regs(0x0E, 0x42); // R7  Interface: master, I2S, 16 bit
    update_codec_regs(0x10, 0x02); // R8  Sampling: normal mode, 384fs, 48 kHz
    update_codec_regs(0x20, 0x7B); // R16 ALC control 1
    update_codec_regs(0x22, 0x32); // R17 ALC control 2
    update_codec_regs(0x24, 0x00); // R18 Noise gate
    usleep(500000);
    update_codec_regs(0x12, 0x01); // R9  Active = 1
}

static void init_effects(void)
{
    /* All effects off; parameters at the GUI's start-up values */
    Effect_Update(REG_EFFECTS_ENABLE, 0x0000);
    Effect_Update(REG_OD_DRIVE,       0);
    Effect_Update(REG_OD_GAIN,        1);
    Effect_Update(REG_TREM_WAVE,      0);
    Effect_Update(REG_TREM_DEPTH,     0);
    Effect_Update(REG_ECHO_TIME,      0);
    Effect_Update(REG_ECHO_REPEAT,    0);
    Effect_Update(REG_ECHO_LEVEL,     1);
    Effect_Update(REG_DIST_MIX,       0);
    Effect_Update(REG_DIST_TYPE,      0);
    Effect_Update(REG_CHORUS_LEVEL,   0);
    Effect_Update(REG_CHORUS_DEPTH,   0);
    Effect_Update(REG_CHORUS_RATE,    0);
    Effect_Update(REG_REVERB_MIX,     0);
    Effect_Update(REG_REVERB_TYPE,    0);
}

int main(void)
{
    alt_u8  frame[FRAME_LEN];
    alt_u32 idle_ms = 0;
    alt_irq_context irq_ctx;

    init_codec();
    init_effects();

    InitUart(UART_BAUD_RATE);
    alt_ic_isr_register(UART_IRQ_INTERRUPT_CONTROLLER_ID, UART_IRQ,
                        handle_UART_interrupts, NULL, NULL);
    alt_ic_irq_enable(UART_IRQ_INTERRUPT_CONTROLLER_ID, UART_IRQ);

    while (1)
    {
        if (frame_ready)
        {
            /* take a consistent copy of the frame, then release the buffer */
            irq_ctx  = alt_irq_disable_all();
            frame[0] = rx_frame[0];
            frame[1] = rx_frame[1];
            frame[2] = rx_frame[2];
            frame_ready = 0;
            alt_irq_enable_all(irq_ctx);

            if (frame[0] == CMD_CODEC_UPDATE)
                update_codec_regs(frame[1], frame[2]);
            else if (frame[0] == CMD_CODEC_PRESET)
                init_codec();
            else
                Effect_Update(frame[0], ((alt_u16)frame[1] << 8) | frame[2]);
            continue;
        }

        /* re-synchronise: drop a partial frame after FRAME_TIMEOUT_MS of silence */
        usleep(1000);
        if (rx_activity) {
            rx_activity = 0;
            idle_ms = 0;
        } else if (rx_index != 0 && ++idle_ms >= FRAME_TIMEOUT_MS) {
            irq_ctx  = alt_irq_disable_all();
            rx_index = 0;
            alt_irq_enable_all(irq_ctx);
            idle_ms  = 0;
        }
    }
    return 0;
}
