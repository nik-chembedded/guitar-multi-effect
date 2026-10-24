using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using define;
using UartApplication;
using KnobControl;

namespace Audio_2
{

    public partial class OverdriveControlForm : Form
    {
        private KnobControl.KnobControl lvlKnob;
        private KnobControl.KnobControl drvKnob;
        private KnobControl.KnobControl tneKnob;
        Uart myport;
        public OverdriveControlForm(Uart port)
        {
            InitializeComponent();
            myport = port;                
        }

        private void driveKnob_ValueChanged(object Sender)
        {
            byte knobVal = 0x00;

            UInt16 val = 0x00;
            UInt16 temp = 0x00;
            val = Convert.ToUInt16(driveKnob.Value);
            byte Low, High;
            temp = val;
            High = Convert.ToByte((temp >> 8));

            temp = val;
            Low = Convert.ToByte(temp & 0x00FF);

            myport.SetEffect(define.constant.ODdrive_ADD, High, Low);
        }

        private void levelKnob_ValueChanged(object Sender)
        {
            UInt16 val = 0x00;
            UInt16 temp = 0x00;
            val = Convert.ToUInt16(levelKnob.Value);
            byte Low, High;
            temp = val;
            High = Convert.ToByte((temp >> 8));

            temp = val;
            Low = Convert.ToByte(temp & 0x00FF);

            myport.SetEffect(define.constant.ODGain_ADD, High, Low);
        }
    }

}
