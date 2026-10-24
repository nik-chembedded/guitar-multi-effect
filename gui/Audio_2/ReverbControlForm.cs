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
    public partial class ReverbControlForm : Form
    {
        private KnobControl.KnobControl mixKnob;
        private KnobControl.KnobControl typeKnob;
        Uart myport;
        public ReverbControlForm(Uart port)
        {
            InitializeComponent();
            myport = port;
        }

        private void knobControl2_ValueChanged(object Sender)
        {
            byte knobVal = 0x00;

            UInt16 val = 0x00;
            UInt16 temp = 0x00;
            val = Convert.ToUInt16(knobControl2.Value);
            byte Low, High;
            temp = val;
            High = Convert.ToByte((temp >> 8));

            temp = val;
            Low = Convert.ToByte(temp & 0x00FF);

            myport.SetEffect(define.constant.ReberbeType_ADD, High, Low);
        }

        private void knobControl1_ValueChanged(object Sender)
        {
            byte knobVal = 0x00;

            UInt16 val = 0x00;
            UInt16 temp = 0x00;
            val = Convert.ToUInt16(knobControl1.Value);
            byte Low, High;
            temp = val;
            High = Convert.ToByte((temp >> 8));

            temp = val;
            Low = Convert.ToByte(temp & 0x00FF);

            myport.SetEffect(define.constant.ReberbeMix_ADD, High, Low);
        }
    }
}
