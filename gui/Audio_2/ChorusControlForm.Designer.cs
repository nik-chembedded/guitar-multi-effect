
namespace Audio_2
{
    partial class ChorusControlForm
    {
        /// <summary>
        /// Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        /// Required method for Designer support - do not modify
        /// the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            this.panel1 = new System.Windows.Forms.Panel();
            this.driveKnob = new KnobControl.KnobControl();
            this.knobControl1 = new KnobControl.KnobControl();
            this.knobControl2 = new KnobControl.KnobControl();
            this.driveLbl = new System.Windows.Forms.Label();
            this.label1 = new System.Windows.Forms.Label();
            this.label2 = new System.Windows.Forms.Label();
            this.SuspendLayout();
            // 
            // panel1
            // 
            this.panel1.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(60)))), ((int)(((byte)(60)))), ((int)(((byte)(100)))));
            this.panel1.Dock = System.Windows.Forms.DockStyle.Top;
            this.panel1.Location = new System.Drawing.Point(0, 0);
            this.panel1.Name = "panel1";
            this.panel1.Size = new System.Drawing.Size(1215, 17);
            this.panel1.TabIndex = 0;
            // 
            // driveKnob
            // 
            this.driveKnob.ForeColor = System.Drawing.Color.Transparent;
            this.driveKnob.ImeMode = System.Windows.Forms.ImeMode.On;
            this.driveKnob.LargeChange = 5;
            this.driveKnob.Location = new System.Drawing.Point(900, 20);
            this.driveKnob.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.driveKnob.Maximum = 65000;
            this.driveKnob.Minimum = 0;
            this.driveKnob.Name = "driveKnob";
            this.driveKnob.ShowLargeScale = false;
            this.driveKnob.ShowSmallScale = false;
            this.driveKnob.Size = new System.Drawing.Size(214, 250);
            this.driveKnob.SmallChange = 1;
            this.driveKnob.TabIndex = 2;
            this.driveKnob.Value = 0;
            this.driveKnob.ValueChanged += new KnobControl.ValueChangedEventHandler(this.driveKnob_ValueChanged);
            // 
            // knobControl1
            // 
            this.knobControl1.ForeColor = System.Drawing.Color.Transparent;
            this.knobControl1.ImeMode = System.Windows.Forms.ImeMode.On;
            this.knobControl1.LargeChange = 5;
            this.knobControl1.Location = new System.Drawing.Point(650, 20);
            this.knobControl1.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.knobControl1.Maximum = 1020;
            this.knobControl1.Minimum = 1;
            this.knobControl1.Name = "knobControl1";
            this.knobControl1.ShowLargeScale = false;
            this.knobControl1.ShowSmallScale = false;
            this.knobControl1.Size = new System.Drawing.Size(214, 250);
            this.knobControl1.SmallChange = 1;
            this.knobControl1.TabIndex = 3;
            this.knobControl1.Value = 0;
            this.knobControl1.ValueChanged += new KnobControl.ValueChangedEventHandler(this.knobControl1_ValueChanged);
            // 
            // knobControl2
            // 
            this.knobControl2.ForeColor = System.Drawing.Color.Transparent;
            this.knobControl2.ImeMode = System.Windows.Forms.ImeMode.On;
            this.knobControl2.LargeChange = 5;
            this.knobControl2.Location = new System.Drawing.Point(400, 20);
            this.knobControl2.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.knobControl2.Maximum = 255;
            this.knobControl2.Minimum = 0;
            this.knobControl2.Name = "knobControl2";
            this.knobControl2.ShowLargeScale = false;
            this.knobControl2.ShowSmallScale = false;
            this.knobControl2.Size = new System.Drawing.Size(214, 250);
            this.knobControl2.SmallChange = 1;
            this.knobControl2.TabIndex = 4;
            this.knobControl2.Value = 0;
            this.knobControl2.ValueChanged += new KnobControl.ValueChangedEventHandler(this.knobControl2_ValueChanged);
            // 
            // driveLbl
            // 
            this.driveLbl.AutoSize = true;
            this.driveLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.driveLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.driveLbl.Location = new System.Drawing.Point(960, 230);
            this.driveLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.driveLbl.Name = "driveLbl";
            this.driveLbl.Size = new System.Drawing.Size(94, 38);
            this.driveLbl.TabIndex = 5;
            this.driveLbl.Text = "LEVEL";
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.label1.ForeColor = System.Drawing.Color.Gainsboro;
            this.label1.Location = new System.Drawing.Point(707, 230);
            this.label1.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(107, 38);
            this.label1.TabIndex = 6;
            this.label1.Text = "DEPTH";
            // 
            // label2
            // 
            this.label2.AutoSize = true;
            this.label2.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.label2.ForeColor = System.Drawing.Color.Gainsboro;
            this.label2.Location = new System.Drawing.Point(468, 230);
            this.label2.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.label2.Name = "label2";
            this.label2.Size = new System.Drawing.Size(84, 38);
            this.label2.TabIndex = 7;
            this.label2.Text = "RATE";
            // 
            // ChorusControlForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(10F, 25F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(35)))), ((int)(((byte)(35)))), ((int)(((byte)(50)))));
            this.ClientSize = new System.Drawing.Size(1215, 450);
            this.Controls.Add(this.label2);
            this.Controls.Add(this.label1);
            this.Controls.Add(this.driveLbl);
            this.Controls.Add(this.knobControl2);
            this.Controls.Add(this.knobControl1);
            this.Controls.Add(this.driveKnob);
            this.Controls.Add(this.panel1);
            this.Name = "ChorusControlForm";
            this.Text = "ChorusControlForm";
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Panel panel1;
        private KnobControl.KnobControl driveKnob;
        private KnobControl.KnobControl knobControl1;
        private KnobControl.KnobControl knobControl2;
        private System.Windows.Forms.Label driveLbl;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.Label label2;
    }
}