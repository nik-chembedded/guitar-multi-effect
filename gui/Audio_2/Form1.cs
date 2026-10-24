using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;
using FontAwesome.Sharp;
using System.IO.Ports;
using define;
using UartApplication;

namespace Audio_2
{
    public partial class Form1 : System.Windows.Forms.Form
    {
        bool Dragging;
        int xPos;
        int yPos;

        private IconButton currentBtn;
        private Panel leftBorderBtn;
        private Form currentChildFrm;
        private Form Emenu, SettMenu;
        private Uart myport;
        private string[] availablePorts;

        public Form1()
        {
            InitializeComponent();   
            leftBorderBtn = new Panel();
            leftBorderBtn.Size = new Size(5, EffectMenuBtn.Size.Height);
            SideMenuPanel.Controls.Add(leftBorderBtn);
            this.DoubleBuffered = true; // reduce flickering of graphics
            this.MaximizedBounds = Screen.FromHandle(this.Handle).WorkingArea;
            this.BackColor = RGBcolors.mybackColor;
            this.WindowState = System.Windows.Forms.FormWindowState.Maximized;


            availablePorts = SerialPort.GetPortNames();
            myport = new Uart(BaudRate: 9600, COM: "COM10");

            build_menus();

        }

        private struct RGBcolors
        {
            public static Color color1 = Color.FromArgb(50, 50, 100);
            public static Color sidePnlBtn = Color.FromArgb(189, 83, 181);
            public static Color HighlightBtn = Color.FromArgb(42, 42, 70);
            public static Color originalBtn = Color.FromArgb(35, 35, 50);
            public static Color mybackColor = Color.FromArgb(35, 35, 50);
        }

        private void ActivateButton(object senderBtn,Color color)
        {
            if(senderBtn != null)
            {
                DissableButton();
                //Button
                currentBtn = (IconButton)senderBtn;
                currentBtn.BackColor = color;
                currentBtn.ForeColor = Color.Silver;
                currentBtn.Font = new Font(currentBtn.Font, FontStyle.Bold);
                //currentBtn.TextAlign = ContentAlignment.MiddleCenter;
                currentBtn.IconColor = Color.Silver;
                //currentBtn.TextImageRelation = TextImageRelation.TextBeforeImage;
                //currentBtn.ImageAlign = ContentAlignment.MiddleRight;
                //Left border button
                leftBorderBtn.BackColor = RGBcolors.sidePnlBtn;
                leftBorderBtn.Location = new Point(0, currentBtn.Location.Y);
                leftBorderBtn.Visible = true;
                leftBorderBtn.BringToFront();

            }
        }

        private void DissableButton()
        {
            if(currentBtn != null)
            {
                currentBtn.BackColor = RGBcolors.originalBtn;
                currentBtn.ForeColor = Color.Gainsboro;
                currentBtn.TextAlign = ContentAlignment.MiddleCenter;
                currentBtn.IconColor = Color.Gainsboro;
                currentBtn.Font = new Font(currentBtn.Font, FontStyle.Regular);
                currentBtn.TextImageRelation = TextImageRelation.ImageBeforeText;
                currentBtn.ImageAlign = ContentAlignment.MiddleLeft;
                
            }
        }

        private void build_menus()
        {
            Emenu = new EffectsForm(myport);
            Emenu.TopLevel = false;
            Emenu.FormBorderStyle = FormBorderStyle.None;
            Emenu.Dock = DockStyle.Fill;
            panelChildForm.Controls.Add(Emenu);
            panelChildForm.Tag = Emenu;
            Emenu.BringToFront();
            Emenu.Hide();

            SettMenu = new SettingsForm(myport, availablePorts);
            SettMenu.TopLevel = false;
            SettMenu.FormBorderStyle = FormBorderStyle.None;
            SettMenu.Dock = DockStyle.Fill;
            panelChildForm.Controls.Add(SettMenu);
            panelChildForm.Tag = SettMenu;
            SettMenu.BringToFront();
            SettMenu.Hide();

        }

        private void OpenChildForm(Form childForm)
        {
            if(currentChildFrm != null)
            {
                //currentChildFrm.Close();
                currentChildFrm.Hide();
            }
            currentChildFrm = childForm;
            childForm.TopLevel = false;
            childForm.FormBorderStyle = FormBorderStyle.None;
            childForm.Dock = DockStyle.Fill;
            panelChildForm.Controls.Add(childForm);
            panelChildForm.Tag = childForm;
            childForm.BringToFront();
            childForm.Show();
        }

        private void Form1_Load(object sender, EventArgs e)
        {
            //ControlExtension.Draggable(label1, true);
            //FormBorderStyle = System.Windows.Forms.FormBorderStyle.Sizable;
            //WindowState = FormWindowState.Maximized;
            //TopMost = true;
            //this.DoubleBuffered = true; // reduce flickering of graphics
        }

        /*private void label1_MouseDown(object sender, MouseEventArgs e)
        {
            if(e.Button == MouseButtons.Left)
            {
                Dragging = true;
                xPos = e.X;
                yPos = e.Y;
            }
        }*/

        /*private void label1_MouseMove(object sender, MouseEventArgs e)
        {
            Control c = sender as Control;
            if (Dragging && c != null)
            {
                if (label1.Location.Y < this.Height - 100)
                {
                    c.Top = e.Y + c.Top - yPos; //  e.Y + c.Top - yPos;
                    c.Left = e.X + c.Left - xPos; //e.X + c.Left - xPos;
                }
                else 
                    c.Top = this.Height - 100;

            }
        }*/

        private void label1_MouseUp(object sender, MouseEventArgs e)
        {
            Dragging = false;
        }

        private void EffectMenuBtn_Click(object sender, EventArgs e)
        {
            ActivateButton(sender, RGBcolors.HighlightBtn);
            //OpenChildForm(new EffectsForm(myport));
            Emenu.Show();
            SettMenu.Hide();
          
        }

        private void SettingsBtn_Click(object sender, EventArgs e)
        {
            ActivateButton(sender, RGBcolors.HighlightBtn);
            //OpenChildForm(new SettingsForm(myport));
            Emenu.Hide();
            SettMenu.Show();
        }

        private void Form1_FormClosing(object sender, FormClosingEventArgs e)
        {
            myport.closeUART();
        }
    }
}
