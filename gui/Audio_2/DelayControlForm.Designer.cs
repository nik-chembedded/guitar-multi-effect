
namespace Audio_2
{
    partial class DelayControlForm
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
            this.levelKnob = new KnobControl.KnobControl();
            this.panel1 = new System.Windows.Forms.Panel();
            this.timeKnob = new KnobControl.KnobControl();
            this.repeatKnob = new KnobControl.KnobControl();
            this.timeLbl = new System.Windows.Forms.Label();
            this.repeatLbl = new System.Windows.Forms.Label();
            this.levelLbl = new System.Windows.Forms.Label();
            this.SuspendLayout();
            // 
            // levelKnob
            // 
            this.levelKnob.ForeColor = System.Drawing.Color.Red;
            this.levelKnob.ImeMode = System.Windows.Forms.ImeMode.On;
            this.levelKnob.LargeChange = 5;
            this.levelKnob.Location = new System.Drawing.Point(900, 20);
            this.levelKnob.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.levelKnob.Maximum = 32000;
            this.levelKnob.Minimum = 0;
            this.levelKnob.Name = "levelKnob";
            this.levelKnob.ShowLargeScale = false;
            this.levelKnob.ShowSmallScale = false;
            this.levelKnob.Size = new System.Drawing.Size(214, 250);
            this.levelKnob.SmallChange = 1;
            this.levelKnob.TabIndex = 0;
            this.levelKnob.Value = 0;
            this.levelKnob.ValueChanged += new KnobControl.ValueChangedEventHandler(this.levelKnob_ValueChanged);
            // 
            // panel1
            // 
            this.panel1.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(60)))), ((int)(((byte)(60)))), ((int)(((byte)(100)))));
            this.panel1.Dock = System.Windows.Forms.DockStyle.Top;
            this.panel1.Location = new System.Drawing.Point(0, 0);
            this.panel1.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.panel1.Name = "panel1";
            this.panel1.Size = new System.Drawing.Size(1184, 17);
            this.panel1.TabIndex = 1;
            // 
            // timeKnob
            // 
            this.timeKnob.ForeColor = System.Drawing.Color.Red;
            this.timeKnob.ImeMode = System.Windows.Forms.ImeMode.On;
            this.timeKnob.LargeChange = 5;
            this.timeKnob.Location = new System.Drawing.Point(400, 20);
            this.timeKnob.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.timeKnob.Maximum = 32760;
            this.timeKnob.Minimum = 500;
            this.timeKnob.Name = "timeKnob";
            this.timeKnob.ShowLargeScale = false;
            this.timeKnob.ShowSmallScale = false;
            this.timeKnob.Size = new System.Drawing.Size(214, 250);
            this.timeKnob.SmallChange = 10;
            this.timeKnob.TabIndex = 2;
            this.timeKnob.Value = 0;
            this.timeKnob.ValueChanged += new KnobControl.ValueChangedEventHandler(this.timeKnob_ValueChanged);
            // 
            // repeatKnob
            // 
            this.repeatKnob.ForeColor = System.Drawing.Color.Red;
            this.repeatKnob.ImeMode = System.Windows.Forms.ImeMode.On;
            this.repeatKnob.LargeChange = 5;
            this.repeatKnob.Location = new System.Drawing.Point(650, 20);
            this.repeatKnob.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.repeatKnob.Maximum = 255;
            this.repeatKnob.Minimum = 0;
            this.repeatKnob.Name = "repeatKnob";
            this.repeatKnob.ShowLargeScale = false;
            this.repeatKnob.ShowSmallScale = false;
            this.repeatKnob.Size = new System.Drawing.Size(214, 250);
            this.repeatKnob.SmallChange = 1;
            this.repeatKnob.TabIndex = 3;
            this.repeatKnob.Value = 0;
            this.repeatKnob.ValueChanged += new KnobControl.ValueChangedEventHandler(this.repeatKnob_ValueChanged);
            // 
            // timeLbl
            // 
            this.timeLbl.AutoSize = true;
            this.timeLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.timeLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.timeLbl.Location = new System.Drawing.Point(468, 230);
            this.timeLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.timeLbl.Name = "timeLbl";
            this.timeLbl.Size = new System.Drawing.Size(84, 38);
            this.timeLbl.TabIndex = 5;
            this.timeLbl.Text = "TIME";
            // 
            // repeatLbl
            // 
            this.repeatLbl.AutoSize = true;
            this.repeatLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.repeatLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.repeatLbl.Location = new System.Drawing.Point(703, 230);
            this.repeatLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.repeatLbl.Name = "repeatLbl";
            this.repeatLbl.Size = new System.Drawing.Size(116, 38);
            this.repeatLbl.TabIndex = 6;
            this.repeatLbl.Text = "REPEAT";
            // 
            // levelLbl
            // 
            this.levelLbl.AutoSize = true;
            this.levelLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.levelLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.levelLbl.Location = new System.Drawing.Point(960, 230);
            this.levelLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.levelLbl.Name = "levelLbl";
            this.levelLbl.Size = new System.Drawing.Size(94, 38);
            this.levelLbl.TabIndex = 7;
            this.levelLbl.Text = "LEVEL";
            // 
            // DelayControlForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(10F, 25F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(35)))), ((int)(((byte)(35)))), ((int)(((byte)(50)))));
            this.ClientSize = new System.Drawing.Size(1184, 602);
            this.Controls.Add(this.levelLbl);
            this.Controls.Add(this.repeatLbl);
            this.Controls.Add(this.timeLbl);
            this.Controls.Add(this.repeatKnob);
            this.Controls.Add(this.timeKnob);
            this.Controls.Add(this.panel1);
            this.Controls.Add(this.levelKnob);
            this.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.Name = "DelayControlForm";
            this.Text = "DelayControlForm";
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private KnobControl.KnobControl levelKnob;
        private System.Windows.Forms.Panel panel1;
        private KnobControl.KnobControl timeKnob;
        private KnobControl.KnobControl repeatKnob;
        private System.Windows.Forms.Label timeLbl;
        private System.Windows.Forms.Label repeatLbl;
        private System.Windows.Forms.Label levelLbl;
    }
}