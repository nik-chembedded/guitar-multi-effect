
namespace Audio_2
{
    partial class ReverbControlForm
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
            this.label1 = new System.Windows.Forms.Label();
            this.knobControl2 = new KnobControl.KnobControl();
            this.driveLbl = new System.Windows.Forms.Label();
            this.knobControl1 = new KnobControl.KnobControl();
            this.SuspendLayout();
            // 
            // panel1
            // 
            this.panel1.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(60)))), ((int)(((byte)(60)))), ((int)(((byte)(100)))));
            this.panel1.Dock = System.Windows.Forms.DockStyle.Top;
            this.panel1.Location = new System.Drawing.Point(0, 0);
            this.panel1.Name = "panel1";
            this.panel1.Size = new System.Drawing.Size(1052, 17);
            this.panel1.TabIndex = 0;
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.label1.ForeColor = System.Drawing.Color.Gainsboro;
            this.label1.Location = new System.Drawing.Point(556, 230);
            this.label1.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(83, 38);
            this.label1.TabIndex = 11;
            this.label1.Text = "TYPE";
            // 
            // knobControl2
            // 
            this.knobControl2.ForeColor = System.Drawing.Color.Red;
            this.knobControl2.ImeMode = System.Windows.Forms.ImeMode.On;
            this.knobControl2.LargeChange = 5;
            this.knobControl2.Location = new System.Drawing.Point(490, 20);
            this.knobControl2.Maximum = 3;
            this.knobControl2.Minimum = 0;
            this.knobControl2.Name = "knobControl2";
            this.knobControl2.ShowLargeScale = false;
            this.knobControl2.ShowSmallScale = true;
            this.knobControl2.Size = new System.Drawing.Size(214, 250);
            this.knobControl2.SmallChange = 1;
            this.knobControl2.TabIndex = 10;
            this.knobControl2.Value = 0;
            this.knobControl2.ValueChanged += new KnobControl.ValueChangedEventHandler(this.knobControl2_ValueChanged);
            // 
            // driveLbl
            // 
            this.driveLbl.AutoSize = true;
            this.driveLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.driveLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.driveLbl.Location = new System.Drawing.Point(850, 230);
            this.driveLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.driveLbl.Name = "driveLbl";
            this.driveLbl.Size = new System.Drawing.Size(71, 38);
            this.driveLbl.TabIndex = 9;
            this.driveLbl.Text = "MIX";
            // 
            // knobControl1
            // 
            this.knobControl1.ForeColor = System.Drawing.Color.Transparent;
            this.knobControl1.ImeMode = System.Windows.Forms.ImeMode.On;
            this.knobControl1.LargeChange = 5;
            this.knobControl1.Location = new System.Drawing.Point(780, 20);
            this.knobControl1.Maximum = 255;
            this.knobControl1.Minimum = 0;
            this.knobControl1.Name = "knobControl1";
            this.knobControl1.ShowLargeScale = true;
            this.knobControl1.ShowSmallScale = false;
            this.knobControl1.Size = new System.Drawing.Size(214, 250);
            this.knobControl1.SmallChange = 1;
            this.knobControl1.TabIndex = 8;
            this.knobControl1.Value = 0;
            this.knobControl1.ValueChanged += new KnobControl.ValueChangedEventHandler(this.knobControl1_ValueChanged);
            // 
            // ReverbControlForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(10F, 25F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(35)))), ((int)(((byte)(35)))), ((int)(((byte)(50)))));
            this.ClientSize = new System.Drawing.Size(1052, 450);
            this.Controls.Add(this.label1);
            this.Controls.Add(this.knobControl2);
            this.Controls.Add(this.driveLbl);
            this.Controls.Add(this.knobControl1);
            this.Controls.Add(this.panel1);
            this.Name = "ReverbControlForm";
            this.Text = "ReverbControlForm";
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Panel panel1;
        private System.Windows.Forms.Label label1;
        private KnobControl.KnobControl knobControl2;
        private System.Windows.Forms.Label driveLbl;
        private KnobControl.KnobControl knobControl1;
    }
}