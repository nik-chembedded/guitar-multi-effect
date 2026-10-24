
namespace Audio_2
{
    partial class OverdriveControlForm
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
            this.driveKnob = new KnobControl.KnobControl();
            this.levelLbl = new System.Windows.Forms.Label();
            this.driveLbl = new System.Windows.Forms.Label();
            this.panel1 = new System.Windows.Forms.Panel();
            this.SuspendLayout();
            // 
            // levelKnob
            // 
            this.levelKnob.Font = new System.Drawing.Font("Segoe UI", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point);
            this.levelKnob.ForeColor = System.Drawing.Color.Red;
            this.levelKnob.ImeMode = System.Windows.Forms.ImeMode.On;
            this.levelKnob.LargeChange = 5;
            this.levelKnob.Location = new System.Drawing.Point(490, 20);
            this.levelKnob.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.levelKnob.Maximum = 5;
            this.levelKnob.Minimum = 1;
            this.levelKnob.Name = "levelKnob";
            this.levelKnob.ShowLargeScale = true;
            this.levelKnob.ShowSmallScale = true;
            this.levelKnob.Size = new System.Drawing.Size(214, 250);
            this.levelKnob.SmallChange = 1;
            this.levelKnob.TabIndex = 0;
            this.levelKnob.Value = 0;
            this.levelKnob.ValueChanged += new KnobControl.ValueChangedEventHandler(this.levelKnob_ValueChanged);
            // 
            // driveKnob
            // 
            this.driveKnob.ForeColor = System.Drawing.Color.Red;
            this.driveKnob.ImeMode = System.Windows.Forms.ImeMode.On;
            this.driveKnob.LargeChange = 5;
            this.driveKnob.Location = new System.Drawing.Point(780, 20);
            this.driveKnob.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.driveKnob.Maximum = 3500;
            this.driveKnob.Minimum = 0;
            this.driveKnob.Name = "driveKnob";
            this.driveKnob.ShowLargeScale = false;
            this.driveKnob.ShowSmallScale = false;
            this.driveKnob.Size = new System.Drawing.Size(214, 250);
            this.driveKnob.SmallChange = 1;
            this.driveKnob.TabIndex = 1;
            this.driveKnob.Value = 0;
            this.driveKnob.ValueChanged += new KnobControl.ValueChangedEventHandler(this.driveKnob_ValueChanged);
            // 
            // levelLbl
            // 
            this.levelLbl.AutoSize = true;
            this.levelLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.levelLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.levelLbl.Location = new System.Drawing.Point(555, 230);
            this.levelLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.levelLbl.Name = "levelLbl";
            this.levelLbl.Size = new System.Drawing.Size(94, 38);
            this.levelLbl.TabIndex = 3;
            this.levelLbl.Text = "LEVEL";
            // 
            // driveLbl
            // 
            this.driveLbl.AutoSize = true;
            this.driveLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.driveLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.driveLbl.Location = new System.Drawing.Point(840, 230);
            this.driveLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.driveLbl.Name = "driveLbl";
            this.driveLbl.Size = new System.Drawing.Size(99, 38);
            this.driveLbl.TabIndex = 4;
            this.driveLbl.Text = "DRIVE";
            // 
            // panel1
            // 
            this.panel1.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(60)))), ((int)(((byte)(60)))), ((int)(((byte)(100)))));
            this.panel1.Dock = System.Windows.Forms.DockStyle.Top;
            this.panel1.Location = new System.Drawing.Point(0, 0);
            this.panel1.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.panel1.Name = "panel1";
            this.panel1.Size = new System.Drawing.Size(1120, 17);
            this.panel1.TabIndex = 6;
            // 
            // OverdriveControlForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(10F, 25F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(35)))), ((int)(((byte)(35)))), ((int)(((byte)(50)))));
            this.ClientSize = new System.Drawing.Size(1120, 602);
            this.Controls.Add(this.panel1);
            this.Controls.Add(this.driveLbl);
            this.Controls.Add(this.levelLbl);
            this.Controls.Add(this.driveKnob);
            this.Controls.Add(this.levelKnob);
            this.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.Name = "OverdriveControlForm";
            this.Text = "overdriveControl";
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private KnobControl.KnobControl levelKnob;
        private KnobControl.KnobControl driveKnob;
        private System.Windows.Forms.Label levelLbl;
        private System.Windows.Forms.Label driveLbl;
        private System.Windows.Forms.Panel panel1;
    }
}