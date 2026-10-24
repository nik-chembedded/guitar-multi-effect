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

namespace Audio_2
{
    public partial class TremoloControlForm : Form
    {
        Uart myport;

        public TremoloControlForm(Uart port)
        {
            InitializeComponent();
            myport = port;
        }

        private void depthKnob_ValueChanged(object Sender)
        {
            byte knobVal = 0x00;

            UInt16 val = 0x00;
            UInt16 temp = 0x00;
            val = Convert.ToUInt16(depthKnob.Value);
            byte Low, High;
            temp = val;
            High = Convert.ToByte((temp >> 8));

            temp = val;
            Low = Convert.ToByte(temp & 0x00FF);

            myport.SetEffect(define.constant.TremDepth_ADD, High, Low);
        }

        private void rateKnob_ValueChanged(object Sender)
        {
            byte knobVal = 0x00;

            UInt16 val = 0x00;
            UInt16 temp = 0x00;
            val = Convert.ToUInt16(rateKnob.Value);
            byte Low, High;
            temp = val;
            High = Convert.ToByte((temp >> 8));

            temp = val;
            Low = Convert.ToByte(temp & 0x00FF);

            myport.SetEffect(define.constant.TremWave_ADD, High, Low);
        }
    }
}
