using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using System.IO.Ports;
using System.Diagnostics;
using System.ServiceProcess;
using define;
using UartApplication;

namespace Audio_2
{
    public partial class SettingsForm : Form
    {

        Byte R0_status = 0x1A;
        Byte R0_addr_stat = Regs.R0;

        Byte R1_status = 0x1A;
        Byte R1_addr_stat = Regs.R1;

        Byte R2_status = 0x7A;
        Byte R2_addr_stat = Regs.R2;
        Byte R3_status = 0x7A;
        Byte R3_addr_stat = Regs.R3;

        Byte R4_status = 0x10;
        Byte R5_status = 0x00;
        Byte R6_status = 0x00;
        Byte R7_status = 0x42;     // UNUSED IN THE GUI, PROGRAMMEMD THROUGH NIOS ONLY
        Byte R8_status = 0x02;     // UNUSED IN THE GUI, PROGRAMMEMD THROUGH NIOS ONLY

        Byte R9_status = 0x01;
        Byte R15_status = 0x00;    // UNUSED IN THE GUI, PROGRAMMEMD THROUGH NIOS ONLY

        Byte R16_status = 0x7B;
        Byte R16_addr_stat = Regs.R16;

        Byte R17_status = 0x32;
        Byte R18_status = 0x00;

        byte codec_addr = 0x00;
        byte codec_data = 0x00;

        private string[] ports;
        Uart myport;
        public SettingsForm(Uart port,string[] availablePorts)
        {
            InitializeComponent();
            myport = port;
            portsBox.Items.AddRange(availablePorts);
            //portsBox.SelectedIndex = 0;
            ports = availablePorts;

            linvolBar.Value = 0x1A;
            rinvolBar.Value = 0x1A;
            lhpvolBar.Value = 0x7A;
            rhpvolBar.Value = 0x7A;
            sidetoneBar.Value = 0x00;
            deemphBar.Value = 0x00;
            atktrackBar.Value = 0x02;
            dcytraclBar.Value = 0x03;
            nggtrackBar.Value = 0x00;
            ngthtrackBar.Value = 0x00;
            alcltrackBar.Value = 0x0B;
            maxgaintracBar.Value = 0x07;
            

        }

        static class Regs
        {
            public const byte R0 = 0x00;
            public const byte R1 = 0x02;
            public const byte R2 = 0x04;
            public const byte R3 = 0x06;
            public const byte R4 = 0x08;
            public const byte R5 = 0x0A;
            public const byte R6 = 0x0C;
            public const byte R7 = 0x0E; // Unused
            public const byte R8 = 0x10; // Unused
            public const byte R9 = 0x12; // Unused
            public const byte R15 = 0x1E;
            public const byte R16 = 0x20;
            public const byte R17 = 0x22;
            public const byte R18 = 0x24;

            public const byte CODEC_ADDRESS = 0xCD;
            public const byte CODEC_PRESET  = 0xEC;
        }

        public void update_codec(byte address,byte data)
        {
            myport.SetCodec(Regs.CODEC_ADDRESS, address, data);
        }
        private void refreshBtn_Click(object sender, EventArgs e)
        {
            portsBox.Items.Clear();
            ports = SerialPort.GetPortNames();
            portsBox.Items.AddRange(ports);
        }

        private void connectBtn_Click(object sender, EventArgs e)
        {
            myport.setPort(portsBox.Text);
        }

        private void linvolBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            int val;
            if (linvolBar.Value < 45)
            {
                temp = (Convert.ToDouble(linvolBar.Value) * 1.5) - 34.5;
            }
            else
            {
                temp = 33;
            }
            linvolLbl.Text = Convert.ToString(temp) + " dB";

            val = linvolBar.Value;
            codec_data = Convert.ToByte(val);
            R0_status = codec_data;
            codec_addr = R0_addr_stat;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr,2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data,2);
        }

        private void rinvolBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            int val;
            if (rinvolBar.Value < 45)
            {
                temp = (Convert.ToDouble(rinvolBar.Value) * 1.5) - 34.5;
            }
            else
            {
                temp = 33;
            }
            rinvolLbl.Text = Convert.ToString(temp) + " dB";

            val = rinvolBar.Value;
            codec_data = Convert.ToByte(val);
            R1_status = codec_data;
            codec_addr = R1_addr_stat;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void lhpvolBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            int val;
            if(lhpvolBar.Value < 48 )
            {
                lhpvolLbl.Text = "mute";
            }
            else
            {
                temp = (Convert.ToDouble(lhpvolBar.Value) * 1) - 73 - 48;
                lhpvolLbl.Text = Convert.ToString(temp) + " dB";
            }

            val = lhpvolBar.Value;
            codec_data = Convert.ToByte(val);
            R2_status = codec_data;
            codec_addr = R2_addr_stat;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void rhpvolBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            int val;
            if (rhpvolBar.Value < 48)
            {
                rhpbolLbl.Text = "mute";
            }
            else
            {
                temp = (Convert.ToDouble(rhpvolBar.Value) * 1) - 73 - 48;
                rhpbolLbl.Text = Convert.ToString(temp) + " dB";
            }

            val = rhpvolBar.Value;
            codec_data = Convert.ToByte(val);
            R3_status = codec_data;
            codec_addr = R3_addr_stat;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void sidetoneBar_ValueChanged(object sender, EventArgs e)
        {
            int temp;
            byte temp_dat;
            temp = (sidetoneBar.Value * (-3)) - 6;
            sidetoneLbl.Text = Convert.ToString(temp) + " dB Sidetone Att";

            temp_dat = (byte)(Convert.ToByte(sidetoneBar.Value) << 6);
            R4_status = (byte)(R4_status & 0x3F);
            codec_data = (byte)(R4_status | temp_dat);

            R4_status = codec_data;
            codec_addr = Regs.R4;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void deemphBar_ValueChanged(object sender, EventArgs e)
        {
            int temp = deemphBar.Value;
            int temp_dat;
            switch (temp)
            {
                case 0: deemphLbl.Text = "no de-emphasis";
                        break;
                case 1: deemphLbl.Text = "32 kHz sampling rate";
                         break;
                case 2: deemphLbl.Text = "44.1 kHz sampling rate";
                        break;
                case 3: deemphLbl.Text = "48 kHz sampling rate";
                        break;
                default: deemphLbl.Text = "no de-emphasis";
                         break;
            }
            temp_dat    = (byte)(Convert.ToByte(deemphBar.Value) << 1);
            R5_status   = (byte)(R5_status & 0xF9);
            codec_data  = (byte)(R5_status | temp_dat);

            R5_status = codec_data;
            codec_addr = Regs.R5;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void button20_Click(object sender, EventArgs e)
        {
            /*System.Diagnostics.Process p = new System.Diagnostics.Process();
            p.StartInfo.FileName = "C:\\Users\\nikit\\Desktop\\SSM2603.pdf";
            p.Start();*/
            var p = new Process();
            p.StartInfo = new ProcessStartInfo(@"cmd.exe")
            {
                RedirectStandardOutput = true,
                UseShellExecute = false,
                Arguments = "/c C:\\Users\\nikit\\Desktop\\SSM2603.pdf"
            };
            p.Start();
            //System.Diagnostics.Process.Start(@"C:\\Users\\nikit\\Desktop\\SSM2603.pdf");

        }

        private void alcltrackBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            byte temp_dat;
            temp = (Convert.ToDouble(alcltrackBar.Value) * 1.5) - 28.5;
            alclLbl.Text = Convert.ToString(temp) + " dBFS";

            temp_dat   = Convert.ToByte(alcltrackBar.Value);
            R16_status = (byte)(R16_status & 0xF0);
            codec_data = (byte)(R16_status | temp_dat);
            R16_status = codec_data;
            codec_addr = R16_addr_stat;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void maxgaintracBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            byte temp_dat;
            temp = (Convert.ToDouble(maxgaintracBar.Value) * 6) - 12;
            maxgaintracLbl.Text = Convert.ToString(temp) + " dB";

            temp_dat   = (byte)(Convert.ToByte(maxgaintracBar.Value) << 4);
            R16_status = (byte)(R16_status & 0x8F);
            codec_data = (byte)(R16_status | temp_dat);
            R16_status = codec_data;
            codec_addr = R16_addr_stat;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void aclseltrackBar_ValueChanged(object sender, EventArgs e)
        {
            int temp = alcseltrackBar.Value;
            byte temp_dat,low_bit,high_bit;
            switch (temp)
            {
                case 0:
                    alcseltrackLbl.Text = "ALC disabled";
                    alcseltrackLbl.Location = new Point(405, 30);
                    break;
                case 1:
                    alcseltrackLbl.Text = "ALC on right only";
                    alcseltrackLbl.Location = new Point(390, 30);
                    break;
                case 2:
                    alcseltrackLbl.Text = "ALC on left only";
                    alcseltrackLbl.Location = new Point(395, 30);
                    break;
                case 3:
                    alcseltrackLbl.Text = "ALC on both channels";
                    alcseltrackLbl.Location = new Point(380, 30);
                    break;
                default:
                    alcseltrackLbl.Text = "ALC disabled";
                    alcseltrackLbl.Location = new Point(405, 30);
                    break;
            }
            temp_dat = Convert.ToByte(alcseltrackBar.Value);
            low_bit  = (byte)((temp_dat & 0x01) << 7);
            high_bit = (byte)((temp_dat & 0x02) >> 1);
            R16_status = (byte)(R16_status & 0x7F);
            codec_data = (byte)(R16_status | low_bit);
            codec_addr = (byte)((Regs.R16 & 0xFE) | high_bit);
            R16_status = codec_data;
            R16_addr_stat = codec_addr;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);

        }

        private void atktrackBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            byte temp_dat;
            int power = atktrackBar.Value;
            temp = Math.Pow(2,power) * 6;
            atkLbl.Text = Convert.ToString(temp) + " ms";

            temp_dat = Convert.ToByte(atktrackBar.Value);
            R17_status = (byte)(R17_status & 0xF0);
            codec_data = (byte)(R17_status | temp_dat);
            codec_addr = Regs.R17;
            R17_status = codec_data;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void dcytraclBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            byte temp_dat;
            int power = dcytraclBar.Value;
            temp = Math.Pow(2, power) * 24;
            dcyLbl.Text = Convert.ToString(temp) + " ms";

            temp_dat = (byte)(Convert.ToByte(dcytraclBar.Value) << 4);
            R17_status = (byte)(R17_status & 0x0F);
            codec_data = (byte)(R17_status | temp_dat);
            codec_addr = Regs.R17;
            R17_status = codec_data;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void nggtrackBar_ValueChanged(object sender, EventArgs e)
        {
            byte temp_dat;
            int temp = nggtrackBar.Value;
            switch (temp)
            {
                case 0:
                    nggtrackLbl.Text = "hold PGA gain constant";
                    nggtrackLbl.Location = new Point(707, 30);
                    break;
                case 1:
                    nggtrackLbl.Text = "hold PGA gain constant";
                    nggtrackLbl.Location = new Point(707, 30);
                    break;
                case 2:
                    nggtrackLbl.Text = "mute output";
                    nggtrackLbl.Location = new Point(750, 30);
                    break;
                case 3:
                    nggtrackLbl.Text = "reserved";
                    nggtrackLbl.Location = new Point(755, 30);
                    break;
                default:
                    nggtrackLbl.Text = "hold PGA gain constant";
                    nggtrackLbl.Location = new Point(707, 30);
                    break;
            }

            temp_dat = (byte)(Convert.ToByte(nggtrackBar.Value) << 1);
            R18_status = (byte)(R18_status & 0xF9);
            codec_data = (byte)(R18_status | temp_dat);
            codec_addr = Regs.R18;
            R18_status = codec_data;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void ngthtrackBar_ValueChanged(object sender, EventArgs e)
        {
            double temp;
            byte temp_dat;
            temp = (Convert.ToDouble(ngthtrackBar.Value) * 1.5) - 76.5;
            ngthtrackLbl.Text = Convert.ToString(temp) + " dBFS";

            temp_dat = (byte)(Convert.ToByte(ngthtrackBar.Value) << 3);
            R18_status = (byte)(R18_status & 0x0F);
            codec_data = (byte)(R18_status | temp_dat);
            codec_addr = Regs.R18;
            R18_status = codec_data;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);

        }

        private void linmuteBtn_Click(object sender, EventArgs e)
        {
            if (linmuteBtn.Text == "LINMUTE\n OFF")
            {
                //codec_addr = Regs.R0 | 0x01;
                codec_data = (byte)(R0_status | 0x80);
                codec_addr = R0_addr_stat;
                linmuteBtn.Text = "LINMUTE\n ON";
            }

            else if (linmuteBtn.Text == "LINMUTE\n ON")
            {
                //codec_addr = Regs.R0 & 0xFE;
                codec_data = (byte)(R0_status & 0x7F);
                codec_addr = R0_addr_stat;
                linmuteBtn.Text = "LINMUTE\n OFF";
            }

            R0_status = codec_data;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
            
            //myport.SetCodec(0xCD, codec_addr, codec_data);
        }

        private void lrinbothBtn_Click(object sender, EventArgs e)
        {
            
            if (lrinbothBtn.Text == "LRINBOTH\n OFF")
            {
                codec_addr = Regs.R0 | 0x01;
                R0_addr_stat = codec_addr;
                lrinbothBtn.Text = "LRINBOTH\n ON";
            }

            else if (lrinbothBtn.Text == "LRINBOTH\n ON")
            {
                codec_addr = Regs.R0 & 0xFE;
                R0_addr_stat = codec_addr;
                lrinbothBtn.Text = "LRINBOTH\n OFF";
            }
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void rinmuteBtn_Click(object sender, EventArgs e)
        {
            if(rinmuteBtn.Text == "RINMUTE\n OFF")
            {
                codec_data = (byte)(R1_status | 0x80);
                codec_addr = R1_addr_stat;
                rinmuteBtn.Text = "RINMUTE\n ON";
            }
            else if(rinmuteBtn.Text == "RINMUTE\n ON")
            {
                codec_data = (byte)(R1_status & 0x7F);
                codec_addr = R1_addr_stat;
                rinmuteBtn.Text = "RINMUTE\n OFF";
            }

            R1_status = codec_data;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void rlinbothBtn_Click(object sender, EventArgs e)
        {
            if(rlinbothBtn.Text == "RLINBOTH\n OFF")
            {
                codec_addr = Regs.R1 | 0x01;
                R1_addr_stat = codec_addr;
                rlinbothBtn.Text = "RLINBOTH\n ON";
            }
            else if(rlinbothBtn.Text == "RLINBOTH\n ON")
            {
                codec_addr = Regs.R1 & 0xFE;
                R1_addr_stat = codec_addr;
                rlinbothBtn.Text = "RLINBOTH\n OFF";
            }
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void lrhpbothBtn_Click(object sender, EventArgs e)
        {
            if (lrhpbothBtn.Text == "LRHPBOTH\n OFF")
            {
                codec_addr = Regs.R2 | 0x01;
                R2_addr_stat = codec_addr;
                lrhpbothBtn.Text = "LRHPBOTH\n ON";
            }
            else if (lrhpbothBtn.Text == "LRHPBOTH\n ON")
            {
                codec_addr = Regs.R2 & 0xFE;
                R2_addr_stat = codec_addr;
                lrhpbothBtn.Text = "LRHPBOTH\n OFF";
            }
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void rlhpbothBtn_Click(object sender, EventArgs e)
        {
            if (rlhpbothBtn.Text == "RLHPBOTH\n OFF")
            {
                codec_addr = Regs.R3 | 0x01;
                R3_addr_stat = codec_addr;
                rlhpbothBtn.Text = "RLHPBOTH\n ON";
            }
            else if (rlhpbothBtn.Text == "RLHPBOTH\n ON")
            {
                codec_addr = Regs.R3 & 0xFE;
                R3_addr_stat = codec_addr;
                rlhpbothBtn.Text = "RLHPBOTH\n OFF";
            }
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void micboostBtn_Click(object sender, EventArgs e)
        {
            if (micboostBtn.Text == "MICBOOST\nOFF")
            {
                codec_data = (byte)(R4_status | 0x01);
                R4_status = codec_data;
                micboostBtn.Text = "MICBOOST\nON";
            }
            else if (micboostBtn.Text == "MICBOOST\nON")
            {
                codec_data = (byte)(R4_status & 0xFE);
                R4_status = codec_data;
                micboostBtn.Text = "MICBOOST\nOFF";
            }

            codec_addr = Regs.R4;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void mutemicBtn_Click(object sender, EventArgs e)
        {
            if (mutemicBtn.Text == "MUTEMIC\nOFF")
            {
                codec_data = (byte)(R4_status | 0x02);
                R4_status = codec_data;
                mutemicBtn.Text = "MUTEMIC\nON";
            }
            else if (mutemicBtn.Text == "MUTEMIC\nON")
            {
                codec_data = (byte)(R4_status & 0xFD);
                R4_status = codec_data;
                mutemicBtn.Text = "MUTEMIC\nOFF";
            }
            codec_addr = Regs.R4;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void inselBtn_Click(object sender, EventArgs e)
        {
            if (inselBtn.Text == "INSEL\nline")
            {
                codec_data = (byte)(R4_status | 0x04);
                R4_status = codec_data;
                inselBtn.Text = "INSEL\nmic";
            }
            else if (inselBtn.Text == "INSEL\nmic")
            {
                codec_data = (byte)(R4_status & 0xFB);
                R4_status = codec_data;
                inselBtn.Text = "INSEL\nline";
            }
            codec_addr = Regs.R4;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void bypassBtn_Click(object sender, EventArgs e)
        {
            if (bypassBtn.Text == "Bypass\nOFF")
            {
                codec_data = (byte)(R4_status | 0x08);
                R4_status = codec_data;
                bypassBtn.Text = "Bypass\nON";
            }
            else if (bypassBtn.Text == "Bypass\nON")
            {
                codec_data = (byte)(R4_status & 0xF7);
                R4_status = codec_data;
                bypassBtn.Text = "Bypass\nOFF";
            }
            codec_addr = Regs.R4;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void dacselBtn_Click(object sender, EventArgs e)
        {
            if (dacselBtn.Text == "DACSEL\nOFF")
            {
                codec_data = (byte)(R4_status | 0x10);
                R4_status = codec_data;
                dacselBtn.Text = "DACSEL\nON";
            }
            else if (dacselBtn.Text == "DACSEL\nON")
            {
                codec_data = (byte)(R4_status & 0xEF);
                R4_status = codec_data;
                dacselBtn.Text = "DACSEL\nOFF";
            }
            codec_addr = Regs.R4;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void sidetoneBtn_Click(object sender, EventArgs e)
        {
            if (sidetoneBtn.Text == "SIDETONE\nOFF")
            {
                codec_data = (byte)(R4_status | 0x20);
                R4_status = codec_data;
                sidetoneBtn.Text = "SIDETONE\nON";
            }
            else if (sidetoneBtn.Text == "SIDETONE\nON")
            {
                codec_data = (byte)(R4_status & 0xDF);
                R4_status = codec_data;
                sidetoneBtn.Text = "SIDETONE\nOFF";
            }
            codec_addr = Regs.R4;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void adchpfBtn_Click(object sender, EventArgs e)
        {
            if (adchpfBtn.Text == "ADCHPF\nOFF")
            {
                codec_data = (byte)(R5_status | 0x01);
                R5_status = codec_data;
                adchpfBtn.Text = "ADCHPF\nON";
            }
            else if (adchpfBtn.Text == "ADCHPF\nON")
            {
                codec_data = (byte)(R5_status & 0xFE);
                R5_status = codec_data;
                adchpfBtn.Text = "ADCHPF\nOFF";
            }
            codec_addr = Regs.R5;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void dacmuBtn_Click(object sender, EventArgs e)
        {
            if (dacmuBtn.Text == "DACMU\nOFF")
            {
                codec_data = (byte)(R5_status | 0x08);
                R5_status = codec_data;
                dacmuBtn.Text = "DACMU\nON";
            }
            else if (dacmuBtn.Text == "DACMU\nON")
            {
                codec_data = (byte)(R5_status & 0xF7);
                R5_status = codec_data;
                dacmuBtn.Text = "DACMU\nOFF";
            }
            codec_addr = Regs.R5;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void hporBtn_Click(object sender, EventArgs e)
        {
            if (hporBtn.Text == "HPOR\nOFF")
            {
                codec_data = (byte)(R5_status | 0x10);
                R5_status = codec_data;
                hporBtn.Text = "HPOR\nON";
            }
            else if (hporBtn.Text == "HPOR\nON")
            {
                codec_data = (byte)(R5_status & 0xEF);
                R5_status = codec_data;
                hporBtn.Text = "HPOR\nOFF";
            }
            codec_addr = Regs.R5;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void ngatBtn_Click(object sender, EventArgs e)
        {
            if (ngatBtn.Text == "NGAT\nOFF")
            {
                codec_data = (byte)(R18_status | 0x01);
                R18_status = codec_data;
                ngatBtn.Text = "NGAT\nON";
            }
            else if (ngatBtn.Text == "NGAT\nON")
            {
                codec_data = (byte)(R18_status & 0xFE);
                R18_status = codec_data;
                ngatBtn.Text = "NGAT\nOFF";
            }
            codec_addr = Regs.R18;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void activeBtn_Click(object sender, EventArgs e)
        {
            if (activeBtn.Text == "Active\nOFF")
            {
                codec_data = (byte)(R9_status | 0x01);
                R9_status = codec_data;
                activeBtn.Text = "Active\nON";
            }
            else if (activeBtn.Text == "Active\nON")
            {
                codec_data = (byte)(R9_status & 0xFE);
                R9_status = codec_data;
                activeBtn.Text = "Active\nOFF";
            }
            codec_addr = Regs.R9;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void lineinBtn_Click(object sender, EventArgs e)
        {
            if (lineinBtn.Text == "LINEIN\nOFF")
            {
                codec_data = (byte)(R6_status & 0xFE);
                R6_status = codec_data;
                lineinBtn.Text = "LINEIN\nON";
            }
            else if (lineinBtn.Text == "LINEIN\nON")
            {
                codec_data = (byte)(R6_status | 0x01);
                R6_status = codec_data;
                lineinBtn.Text = "LINEIN\nOFF";
            }
            codec_addr = Regs.R6;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void micBtn_Click(object sender, EventArgs e)
        {
            if (micBtn.Text == "MIC\nOFF")
            {
                codec_data = (byte)(R6_status & 0xFD);
                R6_status = codec_data;
                micBtn.Text = "MIC\nON";
            }
            else if (micBtn.Text == "MIC\nON")
            {
                codec_data = (byte)(R6_status | 0x02);
                R6_status = codec_data;
                micBtn.Text = "MIC\nOFF";
            }
            codec_addr = Regs.R6;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void adcBtn_Click(object sender, EventArgs e)
        {
            if (adcBtn.Text == "ADC\nOFF")
            {
                codec_data = (byte)(R6_status & 0xFB);
                R6_status = codec_data;
                adcBtn.Text = "ADC\nON";
            }
            else if (adcBtn.Text == "ADC\nON")
            {
                codec_data = (byte)(R6_status | 0x04);
                R6_status = codec_data;
                adcBtn.Text = "ADC\nOFF";
            }
            codec_addr = Regs.R6;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void dacBtn_Click(object sender, EventArgs e)
        {
            if (dacBtn.Text == "DAC\nOFF")
            {
                codec_data = (byte)(R6_status & 0xF7);
                R6_status = codec_data;
                dacBtn.Text = "DAC\nON";
            }
            else if (dacBtn.Text == "DAC\nON")
            {
                codec_data = (byte)(R6_status | 0x08);
                R6_status = codec_data;
                dacBtn.Text = "DAC\nOFF";
            }
            codec_addr = Regs.R6;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void outBtn_Click(object sender, EventArgs e)
        {
            if (outBtn.Text == "Out\nOFF")
            {
                codec_data = (byte)(R6_status & 0xEF);
                R6_status = codec_data;
                outBtn.Text = "Out\nON";
            }
            else if (outBtn.Text == "Out\nON")
            {
                codec_data = (byte)(R6_status | 0x10);
                R6_status = codec_data;
                outBtn.Text = "Out\nOFF";
            }
            codec_addr = Regs.R6;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void oscBtn_Click(object sender, EventArgs e)
        {
            if (oscBtn.Text == "OSC\nOFF")
            {
                codec_data = (byte)(R6_status & 0xDF);
                R6_status = codec_data;
                oscBtn.Text = "OSC\nON";
            }
            else if (oscBtn.Text == "OSC\nON")
            {
                codec_data = (byte)(R6_status | 0x20);
                R6_status = codec_data;
                oscBtn.Text = "OSC\nOFF";
            }
            codec_addr = Regs.R6;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void clkoutBtn_Click(object sender, EventArgs e)
        {
            if (clkoutBtn.Text == "CLKOUT\nOFF")
            {
                codec_data = (byte)(R6_status & 0xBF);
                R6_status = codec_data;
                clkoutBtn.Text = "CLKOUT\nON";
            }
            else if (clkoutBtn.Text == "CLKOUT\nON")
            {
                codec_data = (byte)(R6_status | 0x40);
                R6_status = codec_data;
                clkoutBtn.Text = "CLKOUT\nOFF";
            }
            codec_addr = Regs.R6;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void pwroffBtn_Click(object sender, EventArgs e)
        {
            if (pwroffBtn.Text == "PWROFF\nOFF")
            {
                codec_data = (byte)(R6_status & 0x7F);
                R6_status = codec_data;
                pwroffBtn.Text = "PWROFF\nON";
            }
            else if (pwroffBtn.Text == "PWROFF\nON")
            {
                codec_data = (byte)(R6_status | 0x80);
                R6_status = codec_data;
                pwroffBtn.Text = "PWROFF\nOFF";
            }
            codec_addr = Regs.R6;
            update_codec(codec_addr, codec_data);
            addrLbl.Text = "addr: " + Convert.ToString(codec_addr, 2);
            dataLbl.Text = "data: " + Convert.ToString(codec_data, 2);
        }

        private void presetBtn_Click(object sender, EventArgs e)
        {
            myport.SetCodec(Regs.CODEC_PRESET, 0x00, 0x00);
        }
    }
}
