

#include <stdio.h>
#include "sys/alt_stdio.h"
#include "sys/alt_stdio.h"
#include <stdio.h>
#include <unistd.h>
#include "system.h"
#include "altera_avalon_pio_regs.h"
#include "alt_types.h"
#include "sys/alt_irq.h"
#include "altera_avalon_uart_regs.h"
#include "altera_avalon_uart.h"

#include "my_includes.h"
#include "I2C.h"
#include <unistd.h>

#define effects_enable 0
#define od_drive 1
#define od_gain 2
#define tremolo_wave 3
#define tremolo_depth 4
#define echo_time 5
#define echo_level 7


#define Effect_Update(REG, DATA) \
  IOWR_16DIRECT((REGISTERSCONTROL_0_BASE),(REG*2), (DATA));

#define codec_addr 0x34
#define codec_update 0xCD
#define codec_preset 0xEC


volatile int edge_capture;
alt_u8 buffer_flag = 0;
alt_u8 b_index = 0;

 alt_u16 bufferto_data_format(alt_u8* buffer)
 {
	 alt_u16 data = 0;
	 data = data | buffer[1];
	 data = data << 8;
	 data = data | buffer[2];
	 return data;
 }

static void handle_UART_interrupts(void* context, alt_u32 id)
{
	alt_u8* buffer = (alt_u8*)context;

	if(b_index != 2)
	{
		buffer[b_index] = IORD_ALTERA_AVALON_UART_RXDATA(UART_BASE);
		++b_index;
		buffer_flag = 0;
	}
	else
	{
		buffer[b_index] = IORD_ALTERA_AVALON_UART_RXDATA(UART_BASE);
		buffer_flag = 1;
		b_index = 0;
	}

	 IOWR_ALTERA_AVALON_UART_STATUS(UART_BASE, 0);
}

void i2c_send(alt_u8 adress,alt_u16 data)
{
   alt_u8 addr;
   alt_u8 send_data;
   alt_u8 temp = data >> 8;
   addr = (adress << 1) | temp;
   send_data = data & 0x00FF;
   I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,addr,send_data);
}

void InitUart1(unsigned int BaudRate)
{
unsigned int divisor;
divisor = (ALT_CPU_FREQ/9600) +1;
IOWR_ALTERA_AVALON_UART_DIVISOR(UART_BASE, divisor);
IOWR_ALTERA_AVALON_UART_CONTROL(UART_BASE, ALTERA_AVALON_UART_CONTROL_RRDY_MSK);
}


void update_codec_regs(alt_u8 address,alt_u8 data)
{
	 I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,address,data);
	 //printf("Codec addr : %X\n",address);
	 //printf("Codec data : %X\n",data);
}
void init_codec()
{
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x1E,0x00); // Software Reset Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x12,0x00); // Active Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x00,0x19); // Left-Channel ADC Input Volume Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x02,0x19); // Right-Channel ADC Input Volume Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x04,0x78); // Left-Channel DAC Volume Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x06,0x78); // Right-Channel DAC Volume Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x08,0x10); // Analog Audio Path Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x0A,0x00); // Digital Audio Path Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x0C,0x00); // Power Managment Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x0E,0x42); // Digital Audio I/F Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x10,0x02); // Sampling Rate Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x20,0x7B); // ALC Control 1 Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x22,0x32); // ALC Control 2 Register
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x24,0x00); // Noise Gate Register
	usleep(500000);
	I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x12,0x01); // Active Register
}

int main()
{
  alt_u8 rx_buffer[3] = {'A','B','C'};
  alt_u16 dat = 0;
  alt_u16 addr = 0;
  alt_irq_init(0);
  InitUart1(9600);
  alt_ic_isr_register(UART_IRQ_INTERRUPT_CONTROLLER_ID,UART_IRQ,handle_UART_interrupts,rx_buffer,0);
  alt_ic_irq_enable(UART_IRQ_INTERRUPT_CONTROLLER_ID,UART_IRQ);
  //printf("Hello from Nios II!\n");
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x1E,0x00);	// Software Reset Register 					- R15
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x12,0x00);	// Active Register							- R9
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x00,0x19);	// Left-Channel ADC Input Volume Register   - R0
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x02,0x19);  	// Right-Channel ADC Input Volume Register  - R1
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x04,0x78);	// Left-Channel DAC Volume Register			- R2
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x06,0x78);	// Right-Channel DAC Volume Register		- R3
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x08,0x10);	// Analog Audio Path Register				- R4           CHECK WHY ITS 0x10
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x0A,0x00);	// Digital Audio Path Register				- R5
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x0C,0x00);	// Power Managment Register					- R6
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x0E,0x42);	// Digital Audio I/F Register				- R7
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x10,0x02);	// Sampling Rate Register					- R8
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x20,0x7B);	// ALC Control 1 Register					- R16
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x22,0x32);	// ALC Control 2 Register					- R17
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x24,0x00);	// Noise Gate Register						- R18

  usleep(500000);
  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x12,0x01);    // Active Register

	  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x00,0x1A); //1E
	  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x02,0x1A);

	  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x04,0x7A); //7C
	  I2C_Write(I2C_SCL_BASE,I2C_SDA_BASE,codec_addr,0x06,0x7A);

	  Effect_Update(effects_enable,0x0000);
	  Effect_Update(od_drive,0);
	  Effect_Update(od_gain,1);
	  Effect_Update(tremolo_wave,0x0000);
	  Effect_Update(tremolo_depth,0x0000);
	  Effect_Update(echo_time,0x0000);
	  Effect_Update(echo_level,0x0001);

	  while(1)
	  {
			 if(buffer_flag)
			 {
				 addr = rx_buffer[0];
				 if(rx_buffer[0] == codec_update)
					 update_codec_regs(rx_buffer[1],rx_buffer[2]);
				 else if(rx_buffer[0] == codec_preset)
					 init_codec();
				 else
				 {
					 dat = bufferto_data_format(rx_buffer);
					 Effect_Update(addr,dat);
					 //printf("Regs addr : %X\n",rx_buffer[0]);
					 //printf("Regs data : %X\n",dat);
				 }
				 buffer_flag = 0;
				 b_index = 0 ;
			 }
	  }
  return 0;
}

