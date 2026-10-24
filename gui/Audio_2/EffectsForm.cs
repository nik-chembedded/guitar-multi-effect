using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using UartApplication;

namespace Audio_2
{
    public partial class EffectsForm : Form
    {
        bool od_enabled = false;
        bool echo_enabled = false;
        bool tremolo_enabled = false;
        bool dist_enabled = false;
        bool chorus_enabled = false;
        bool reverb_enabled = false;

        byte od_enabledMask = 0x00;
        byte echo_enabledMask = 0x00;
        byte tremolo_enabledMask = 0x00;
        byte dist_enabledMask = 0x00;
        byte chorus_enabledMask = 0x00;
        byte reverb_enabledMask = 0x00;


        byte enablestatus = 0x00 ;

        private Form od_knobs, trem_knobs, echo_knobs, dist_knobs, chorus_knobs, reverb_knobs;

        Uart myport;

        private Form currentChildFrm;
        public EffectsForm(Uart port)
        {
            InitializeComponent();
            this.DoubleBuffered = true; // reduce flickering of graphics
            this.MaximizedBounds = Screen.FromHandle(this.Handle).WorkingArea;
            this.BackColor = RGBcolors.mybackColor;
            
            //Init Button Text
            odEnableBtn.Text = "OFF";
            echoEnBtn.Text = "OFF";
            tremoloEnBtn.Text = "OFF";
            myport = port;
            build_knobs();
        }

        private struct RGBcolors
        {
            public static Color color1 = Color.FromArgb(50, 50, 100);
            public static Color sidePnlBtn = Color.FromArgb(189, 83, 181);
            public static Color HighlightBtn = Color.FromArgb(42, 42, 70);
            public static Color pressedColor = Color.FromArgb(105, 102, 150);
            public static Color originalBtn = Color.FromArgb(35, 35, 50);
            public static Color mybackColor = Color.FromArgb(35, 35, 50);
        }

        private void build_knobs()
        {
            od_knobs = new OverdriveControlForm(myport);
            od_knobs.TopLevel = false;
            od_knobs.FormBorderStyle = FormBorderStyle.None;
            od_knobs.Dock = DockStyle.Fill;
            parametersPanel.Controls.Add(od_knobs);
            parametersPanel.Tag = od_knobs;
            od_knobs.BringToFront();
            od_knobs.Hide();

            trem_knobs = new TremoloControlForm(myport);
            trem_knobs.TopLevel = false;
            trem_knobs.FormBorderStyle = FormBorderStyle.None;
            trem_knobs.Dock = DockStyle.Fill;
            parametersPanel.Controls.Add(trem_knobs);
            parametersPanel.Tag = trem_knobs;
            trem_knobs.BringToFront();
            trem_knobs.Hide();

            echo_knobs = new DelayControlForm(myport);
            echo_knobs.TopLevel = false;
            echo_knobs.FormBorderStyle = FormBorderStyle.None;
            echo_knobs.Dock = DockStyle.Fill;
            parametersPanel.Controls.Add(echo_knobs);
            parametersPanel.Tag = echo_knobs;
            echo_knobs.BringToFront();
            echo_knobs.Hide();

            dist_knobs = new DistortionControlForm(myport);
            dist_knobs.TopLevel = false;
            dist_knobs.FormBorderStyle = FormBorderStyle.None;
            dist_knobs.Dock = DockStyle.Fill;
            parametersPanel.Controls.Add(dist_knobs);
            parametersPanel.Tag = dist_knobs;
            dist_knobs.BringToFront();
            dist_knobs.Hide();

            chorus_knobs = new ChorusControlForm(myport);
            chorus_knobs.TopLevel = false;
            chorus_knobs.FormBorderStyle = FormBorderStyle.None;
            chorus_knobs.Dock = DockStyle.Fill;
            parametersPanel.Controls.Add(chorus_knobs);
            parametersPanel.Tag = chorus_knobs;
            chorus_knobs.BringToFront();
            chorus_knobs.Hide();

            reverb_knobs = new ReverbControlForm(myport);
            reverb_knobs.TopLevel = false;
            reverb_knobs.FormBorderStyle = FormBorderStyle.None;
            reverb_knobs.Dock = DockStyle.Fill;
            parametersPanel.Controls.Add(reverb_knobs);
            parametersPanel.Tag = reverb_knobs;
            reverb_knobs.BringToFront();
            reverb_knobs.Hide();
        }

        private void OpenChildForm(Form childForm)
        {
            if (currentChildFrm != null)
            {
                currentChildFrm.Close();
            }
            currentChildFrm = childForm;
            childForm.TopLevel = false;
            childForm.FormBorderStyle = FormBorderStyle.None;
            childForm.Dock = DockStyle.Fill;
            parametersPanel.Controls.Add(childForm);
            parametersPanel.Tag = childForm;
            childForm.BringToFront();
            childForm.Show();
        }

        private void overdrivePctrBox_Click(object sender, EventArgs e)
        {
            //Effect background color after click
              overdrivePctrBox.BackColor = RGBcolors.pressedColor;
              tremoloPctrBox.BackColor = RGBcolors.mybackColor;
              delayPctrBox.BackColor = RGBcolors.mybackColor;
            reverbPctrBox.BackColor = RGBcolors.mybackColor;
            chorusPctrBox.BackColor = RGBcolors.mybackColor;
            distortionPctrBox.BackColor = RGBcolors.mybackColor;
            //Open Coresponding Control Form
            //OpenChildForm(new OverdriveControlForm(myport));
            od_knobs.Show();
            trem_knobs.Hide();
            echo_knobs.Hide();
            dist_knobs.Hide();
            chorus_knobs.Hide();
            reverb_knobs.Hide();
        }

        private void tremoloPctrBox_Click(object sender, EventArgs e)
        {
            //Effect background color after click
            overdrivePctrBox.BackColor = RGBcolors.mybackColor;
            tremoloPctrBox.BackColor = RGBcolors.pressedColor;
            delayPctrBox.BackColor = RGBcolors.mybackColor;
            reverbPctrBox.BackColor = RGBcolors.mybackColor;
            chorusPctrBox.BackColor = RGBcolors.mybackColor;
            distortionPctrBox.BackColor = RGBcolors.mybackColor;
            //Open Coresponding Control Form
            //OpenChildForm(new TremoloControlForm(myport));
            od_knobs.Hide();
            trem_knobs.Show();
            echo_knobs.Hide();
            dist_knobs.Hide();
            chorus_knobs.Hide();
            reverb_knobs.Hide();
        }

        private void distortionPctrBox_Click(object sender, EventArgs e)
        {
            distortionPctrBox.BackColor = RGBcolors.pressedColor;

            tremoloPctrBox.BackColor = RGBcolors.mybackColor;
            delayPctrBox.BackColor = RGBcolors.mybackColor;
            overdrivePctrBox.BackColor = RGBcolors.mybackColor;
            reverbPctrBox.BackColor = RGBcolors.mybackColor;
            chorusPctrBox.BackColor = RGBcolors.mybackColor;



            od_knobs.Hide();
            trem_knobs.Hide();
            echo_knobs.Hide();
            dist_knobs.Show();
            chorus_knobs.Hide();
            reverb_knobs.Hide();
        }

        private void chorusPctrBox_Click(object sender, EventArgs e)
        {
            chorusPctrBox.BackColor = RGBcolors.pressedColor;

            tremoloPctrBox.BackColor = RGBcolors.mybackColor;
            delayPctrBox.BackColor = RGBcolors.mybackColor;
            overdrivePctrBox.BackColor = RGBcolors.mybackColor;
            reverbPctrBox.BackColor = RGBcolors.mybackColor;          
            distortionPctrBox.BackColor = RGBcolors.mybackColor;

            od_knobs.Hide();
            trem_knobs.Hide();
            echo_knobs.Hide();
            dist_knobs.Hide();
            chorus_knobs.Show();
            reverb_knobs.Hide();
        }

        private void reverbPctrBox_Click(object sender, EventArgs e)
        {           
            reverbPctrBox.BackColor = RGBcolors.pressedColor;

            tremoloPctrBox.BackColor = RGBcolors.mybackColor;
            delayPctrBox.BackColor = RGBcolors.mybackColor;
            overdrivePctrBox.BackColor = RGBcolors.mybackColor;
            chorusPctrBox.BackColor = RGBcolors.mybackColor;
            distortionPctrBox.BackColor = RGBcolors.mybackColor;

            od_knobs.Hide();
            trem_knobs.Hide();
            echo_knobs.Hide();
            dist_knobs.Hide();
            chorus_knobs.Hide();
            reverb_knobs.Show();
        }

        private void distEnBtn_Click(object sender, EventArgs e)
        {
            var temp = 0x00;

            if (dist_enabled == false)
            {
                dist_enabledMask = 0x01;
                //distortionPctrBox.BackColor = Color.Green;
                distEnBtn.Text = "ON";
                dist_enabled = true;
                enablestatus = (byte)(enablestatus | 0x08);
            }
            else
            {
                dist_enabledMask = 0x00;
                distortionPctrBox.BackColor = RGBcolors.mybackColor;
                distEnBtn.Text = "OFF";
                dist_enabled = false;
                enablestatus = (byte)(enablestatus & 0xF7);
            }
            
            myport.SetEffect(define.constant.EffectsEnable_ADD, 0x00, enablestatus);
            label1.Text = Convert.ToString(enablestatus);
        }

        private void chorusEnBtn_Click(object sender, EventArgs e)
        {
            var temp = 0x00;

            if (chorus_enabled == false)
            {
                chorus_enabledMask = 0x01;
                //chorusPctrBox.BackColor = Color.Green;
                chorusEnBtn.Text = "ON";
                chorus_enabled = true;
                enablestatus = (byte)(enablestatus | 0x10);
            }
            else
            {
                chorus_enabledMask = 0x00;
                chorusPctrBox.BackColor = RGBcolors.mybackColor;
                chorusEnBtn.Text = "OFF";
                chorus_enabled = false;
                enablestatus = (byte)(enablestatus & 0xEF);
            }

            myport.SetEffect(define.constant.EffectsEnable_ADD, 0x00, enablestatus);
            label1.Text = Convert.ToString(enablestatus);

        }

        private void reverbEnBtn_Click(object sender, EventArgs e)
        {
            var temp = 0x00;

            if (reverb_enabled == false)
            {
                reverb_enabledMask = 0x01;
                //reverbPctrBox.BackColor = Color.Green;
                reverbEnBtn.Text = "ON";
                reverb_enabled = true;
                enablestatus = (byte)(enablestatus | 0x20);
            }
            else
            {
                reverb_enabledMask = 0x00;
                reverbPctrBox.BackColor = RGBcolors.mybackColor;
                reverbEnBtn.Text = "OFF";
                reverb_enabled = false;
                enablestatus = (byte)(enablestatus & 0xDF);
            }

            myport.SetEffect(define.constant.EffectsEnable_ADD, 0x00, enablestatus);
            label1.Text = Convert.ToString(enablestatus);
        }

        private void delayPctrBox_Click(object sender, EventArgs e)
        {
            //Effect background color after click
            tremoloPctrBox.BackColor = RGBcolors.mybackColor;
            overdrivePctrBox.BackColor = RGBcolors.mybackColor;
            reverbPctrBox.BackColor = RGBcolors.mybackColor;
            distortionPctrBox.BackColor = RGBcolors.mybackColor;
            delayPctrBox.BackColor = RGBcolors.pressedColor;
            chorusPctrBox.BackColor = RGBcolors.mybackColor;

            //Open Coresponding Control Form
            //OpenChildForm(new DelayControlForm(myport));
            od_knobs.Hide();
            trem_knobs.Hide();
            echo_knobs.Show();
            dist_knobs.Hide();
            chorus_knobs.Hide();
            reverb_knobs.Hide();
        }

        private void odEnableBtn_Click(object sender, EventArgs e)
        {
            var temp = 0x00;

            if (od_enabled == false)
            {
                od_enabledMask = 0x01;
                //overdrivePctrBox.BackColor = Color.Green;
                odEnableBtn.Text = "ON";
                od_enabled = true;
                enablestatus = (byte)(enablestatus | 0x01);

            }
            else
            {
                od_enabledMask = 0x00;
                overdrivePctrBox.BackColor = RGBcolors.mybackColor;
                odEnableBtn.Text = "OFF";
                od_enabled = false;
                enablestatus = (byte)(enablestatus & 0xFE);
            }

            //enablestatus = 0x00;
            //temp = (echo_enabledMask << 1);
            //temp = (temp | tremolo_enabledMask) << 1;
            //temp = temp | od_enabledMask;
            //enablestatus = Convert.ToByte(temp);
            myport.SetEffect(define.constant.EffectsEnable_ADD, 0x00, enablestatus);
            label1.Text = Convert.ToString(enablestatus);

        }

        private void tremoloEnBtn_Click(object sender, EventArgs e)
        {
            var temp = 0x00;

            if (tremolo_enabled == false)
            {
                tremolo_enabledMask = 0x01;
                //tremoloPctrBox.BackColor = Color.Green;
                tremoloEnBtn.Text = "ON";
                tremolo_enabled = true;
                enablestatus = (byte)(enablestatus | 0x02);
            }
            else
            {
                tremolo_enabledMask = 0x00;
                tremoloPctrBox.BackColor = RGBcolors.mybackColor;
                tremoloEnBtn.Text = "OFF";
                tremolo_enabled = false;
                enablestatus = (byte)(enablestatus & 0xFD);
            }

            //enablestatus = 0x00;
            //temp = (echo_enabledMask << 1);
            //temp = (temp | tremolo_enabledMask) << 1;
            //temp = temp | od_enabledMask;
            //enablestatus = Convert.ToByte(temp);
            myport.SetEffect(define.constant.EffectsEnable_ADD, 0x00, enablestatus);
            label1.Text = Convert.ToString(enablestatus);

        }



        private void echoEnBtn_Click(object sender, EventArgs e)
        {
            var temp = 0x00;

            if(echo_enabled == false)
            {
                echo_enabledMask = 0x01;
                //delayPctrBox.BackColor = Color.Green;
                echoEnBtn.Text = "ON";
                echo_enabled = true;
                enablestatus = (byte)(enablestatus | 0x04);
            }
            else
            {
                echo_enabledMask = 0x00;
                delayPctrBox.BackColor = RGBcolors.mybackColor;
                echoEnBtn.Text = "OFF";
                echo_enabled = false;
                enablestatus = (byte)(enablestatus & 0xFB);
            }

            //enablestatus = 0x00;
            //temp = (echo_enabledMask << 1);
            //temp = (temp | tremolo_enabledMask) << 1;
            //temp = temp | od_enabledMask;
            //enablestatus = Convert.ToByte(temp);
            myport.SetEffect(define.constant.EffectsEnable_ADD, 0x00, enablestatus);
            label1.Text = Convert.ToString(enablestatus);
        }

        private void EffectsForm_FormClosing(object sender, FormClosingEventArgs e)
        {
            //myport.closeUART();
        }
    }
}
