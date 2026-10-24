
namespace Audio_2
{
    partial class TremoloControlForm
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
            this.depthKnob = new KnobControl.KnobControl();
            this.rateKnob = new KnobControl.KnobControl();
            this.rateLbl = new System.Windows.Forms.Label();
            this.depthLbl = new System.Windows.Forms.Label();
            this.panel1 = new System.Windows.Forms.Panel();
            this.SuspendLayout();
            // 
            // depthKnob
            // 
            this.depthKnob.ForeColor = System.Drawing.Color.Red;
            this.depthKnob.ImeMode = System.Windows.Forms.ImeMode.On;
            this.depthKnob.LargeChange = 5;
            this.depthKnob.Location = new System.Drawing.Point(780, 20);
            this.depthKnob.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.depthKnob.Maximum = 255;
            this.depthKnob.Minimum = 0;
            this.depthKnob.Name = "depthKnob";
            this.depthKnob.ShowLargeScale = false;
            this.depthKnob.ShowSmallScale = false;
            this.depthKnob.Size = new System.Drawing.Size(214, 250);
            this.depthKnob.SmallChange = 1;
            this.depthKnob.TabIndex = 0;
            this.depthKnob.Value = 0;
            this.depthKnob.ValueChanged += new KnobControl.ValueChangedEventHandler(this.depthKnob_ValueChanged);
            // 
            // rateKnob
            // 
            this.rateKnob.ForeColor = System.Drawing.Color.Red;
            this.rateKnob.ImeMode = System.Windows.Forms.ImeMode.On;
            this.rateKnob.LargeChange = 1;
            this.rateKnob.Location = new System.Drawing.Point(490, 20);
            this.rateKnob.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.rateKnob.Maximum = 7;
            this.rateKnob.Minimum = 0;
            this.rateKnob.Name = "rateKnob";
            this.rateKnob.ShowLargeScale = true;
            this.rateKnob.ShowSmallScale = false;
            this.rateKnob.Size = new System.Drawing.Size(214, 250);
            this.rateKnob.SmallChange = 0;
            this.rateKnob.TabIndex = 1;
            this.rateKnob.Value = 0;
            this.rateKnob.ValueChanged += new KnobControl.ValueChangedEventHandler(this.rateKnob_ValueChanged);
            // 
            // rateLbl
            // 
            this.rateLbl.AutoSize = true;
            this.rateLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.rateLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.rateLbl.Location = new System.Drawing.Point(553, 230);
            this.rateLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.rateLbl.Name = "rateLbl";
            this.rateLbl.Size = new System.Drawing.Size(96, 38);
            this.rateLbl.TabIndex = 3;
            this.rateLbl.Text = "WAVE";
            // 
            // depthLbl
            // 
            this.depthLbl.AutoSize = true;
            this.depthLbl.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.depthLbl.ForeColor = System.Drawing.Color.Gainsboro;
            this.depthLbl.Location = new System.Drawing.Point(836, 230);
            this.depthLbl.Margin = new System.Windows.Forms.Padding(4, 0, 4, 0);
            this.depthLbl.Name = "depthLbl";
            this.depthLbl.Size = new System.Drawing.Size(107, 38);
            this.depthLbl.TabIndex = 4;
            this.depthLbl.Text = "DEPTH";
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
            // TremoloControlForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(10F, 25F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(35)))), ((int)(((byte)(35)))), ((int)(((byte)(50)))));
            this.ClientSize = new System.Drawing.Size(1120, 602);
            this.Controls.Add(this.panel1);
            this.Controls.Add(this.depthLbl);
            this.Controls.Add(this.rateLbl);
            this.Controls.Add(this.rateKnob);
            this.Controls.Add(this.depthKnob);
            this.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.Name = "TremoloControlForm";
            this.Text = "tremoloControl";
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private KnobControl.KnobControl depthKnob;
        private KnobControl.KnobControl rateKnob;
        private System.Windows.Forms.Label rateLbl;
        private System.Windows.Forms.Label depthLbl;
        private System.Windows.Forms.Panel panel1;
    }
}