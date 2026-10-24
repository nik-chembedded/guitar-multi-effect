
namespace Audio_2
{
    partial class EffectsForm
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
            System.ComponentModel.ComponentResourceManager resources = new System.ComponentModel.ComponentResourceManager(typeof(EffectsForm));
            this.overdrivePctrBox = new System.Windows.Forms.PictureBox();
            this.tremoloPctrBox = new System.Windows.Forms.PictureBox();
            this.delayPctrBox = new System.Windows.Forms.PictureBox();
            this.parametersPanel = new System.Windows.Forms.Panel();
            this.odEnableBtn = new System.Windows.Forms.Button();
            this.tremoloEnBtn = new System.Windows.Forms.Button();
            this.echoEnBtn = new System.Windows.Forms.Button();
            this.label1 = new System.Windows.Forms.Label();
            this.distortionPctrBox = new System.Windows.Forms.PictureBox();
            this.reverbPctrBox = new System.Windows.Forms.PictureBox();
            this.chorusPctrBox = new System.Windows.Forms.PictureBox();
            this.chorusEnBtn = new System.Windows.Forms.Button();
            this.label2 = new System.Windows.Forms.Label();
            this.label3 = new System.Windows.Forms.Label();
            this.label4 = new System.Windows.Forms.Label();
            this.label5 = new System.Windows.Forms.Label();
            this.label6 = new System.Windows.Forms.Label();
            this.label7 = new System.Windows.Forms.Label();
            this.distEnBtn = new System.Windows.Forms.Button();
            this.reverbEnBtn = new System.Windows.Forms.Button();
            ((System.ComponentModel.ISupportInitialize)(this.overdrivePctrBox)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.tremoloPctrBox)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.delayPctrBox)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.distortionPctrBox)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.reverbPctrBox)).BeginInit();
            ((System.ComponentModel.ISupportInitialize)(this.chorusPctrBox)).BeginInit();
            this.SuspendLayout();
            // 
            // overdrivePctrBox
            // 
            this.overdrivePctrBox.Image = ((System.Drawing.Image)(resources.GetObject("overdrivePctrBox.Image")));
            this.overdrivePctrBox.InitialImage = ((System.Drawing.Image)(resources.GetObject("overdrivePctrBox.InitialImage")));
            this.overdrivePctrBox.Location = new System.Drawing.Point(1145, 180);
            this.overdrivePctrBox.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.overdrivePctrBox.Name = "overdrivePctrBox";
            this.overdrivePctrBox.Size = new System.Drawing.Size(198, 266);
            this.overdrivePctrBox.SizeMode = System.Windows.Forms.PictureBoxSizeMode.CenterImage;
            this.overdrivePctrBox.TabIndex = 0;
            this.overdrivePctrBox.TabStop = false;
            this.overdrivePctrBox.Click += new System.EventHandler(this.overdrivePctrBox_Click);
            // 
            // tremoloPctrBox
            // 
            this.tremoloPctrBox.Image = ((System.Drawing.Image)(resources.GetObject("tremoloPctrBox.Image")));
            this.tremoloPctrBox.Location = new System.Drawing.Point(508, 180);
            this.tremoloPctrBox.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.tremoloPctrBox.Name = "tremoloPctrBox";
            this.tremoloPctrBox.Size = new System.Drawing.Size(191, 262);
            this.tremoloPctrBox.SizeMode = System.Windows.Forms.PictureBoxSizeMode.CenterImage;
            this.tremoloPctrBox.TabIndex = 1;
            this.tremoloPctrBox.TabStop = false;
            this.tremoloPctrBox.Click += new System.EventHandler(this.tremoloPctrBox_Click);
            // 
            // delayPctrBox
            // 
            this.delayPctrBox.Image = ((System.Drawing.Image)(resources.GetObject("delayPctrBox.Image")));
            this.delayPctrBox.Location = new System.Drawing.Point(308, 180);
            this.delayPctrBox.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.delayPctrBox.Name = "delayPctrBox";
            this.delayPctrBox.Size = new System.Drawing.Size(183, 264);
            this.delayPctrBox.SizeMode = System.Windows.Forms.PictureBoxSizeMode.CenterImage;
            this.delayPctrBox.TabIndex = 2;
            this.delayPctrBox.TabStop = false;
            this.delayPctrBox.Click += new System.EventHandler(this.delayPctrBox_Click);
            // 
            // parametersPanel
            // 
            this.parametersPanel.Dock = System.Windows.Forms.DockStyle.Bottom;
            this.parametersPanel.Location = new System.Drawing.Point(0, 643);
            this.parametersPanel.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.parametersPanel.Name = "parametersPanel";
            this.parametersPanel.Size = new System.Drawing.Size(1789, 407);
            this.parametersPanel.TabIndex = 3;
            // 
            // odEnableBtn
            // 
            this.odEnableBtn.BackColor = System.Drawing.Color.Transparent;
            this.odEnableBtn.BackgroundImage = ((System.Drawing.Image)(resources.GetObject("odEnableBtn.BackgroundImage")));
            this.odEnableBtn.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.odEnableBtn.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.odEnableBtn.Location = new System.Drawing.Point(1186, 347);
            this.odEnableBtn.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.odEnableBtn.Name = "odEnableBtn";
            this.odEnableBtn.Size = new System.Drawing.Size(116, 71);
            this.odEnableBtn.TabIndex = 4;
            this.odEnableBtn.Text = "OFF";
            this.odEnableBtn.UseVisualStyleBackColor = false;
            this.odEnableBtn.Click += new System.EventHandler(this.odEnableBtn_Click);
            // 
            // tremoloEnBtn
            // 
            this.tremoloEnBtn.BackColor = System.Drawing.Color.Transparent;
            this.tremoloEnBtn.BackgroundImage = ((System.Drawing.Image)(resources.GetObject("tremoloEnBtn.BackgroundImage")));
            this.tremoloEnBtn.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.tremoloEnBtn.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.tremoloEnBtn.Location = new System.Drawing.Point(548, 339);
            this.tremoloEnBtn.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.tremoloEnBtn.Name = "tremoloEnBtn";
            this.tremoloEnBtn.Size = new System.Drawing.Size(113, 78);
            this.tremoloEnBtn.TabIndex = 5;
            this.tremoloEnBtn.Text = "OFF";
            this.tremoloEnBtn.UseVisualStyleBackColor = false;
            this.tremoloEnBtn.Click += new System.EventHandler(this.tremoloEnBtn_Click);
            // 
            // echoEnBtn
            // 
            this.echoEnBtn.BackColor = System.Drawing.Color.Transparent;
            this.echoEnBtn.BackgroundImage = ((System.Drawing.Image)(resources.GetObject("echoEnBtn.BackgroundImage")));
            this.echoEnBtn.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.echoEnBtn.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.echoEnBtn.Location = new System.Drawing.Point(347, 346);
            this.echoEnBtn.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.echoEnBtn.Name = "echoEnBtn";
            this.echoEnBtn.Size = new System.Drawing.Size(105, 67);
            this.echoEnBtn.TabIndex = 6;
            this.echoEnBtn.Text = "OFF";
            this.echoEnBtn.UseVisualStyleBackColor = false;
            this.echoEnBtn.Click += new System.EventHandler(this.echoEnBtn_Click);
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Font = new System.Drawing.Font("Segoe UI", 20F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point);
            this.label1.ForeColor = System.Drawing.Color.White;
            this.label1.Location = new System.Drawing.Point(21, 9);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(0, 54);
            this.label1.TabIndex = 7;
            this.label1.Visible = false;
            // 
            // distortionPctrBox
            // 
            this.distortionPctrBox.Image = ((System.Drawing.Image)(resources.GetObject("distortionPctrBox.Image")));
            this.distortionPctrBox.Location = new System.Drawing.Point(933, 180);
            this.distortionPctrBox.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.distortionPctrBox.Name = "distortionPctrBox";
            this.distortionPctrBox.Size = new System.Drawing.Size(204, 266);
            this.distortionPctrBox.SizeMode = System.Windows.Forms.PictureBoxSizeMode.CenterImage;
            this.distortionPctrBox.TabIndex = 8;
            this.distortionPctrBox.TabStop = false;
            this.distortionPctrBox.Click += new System.EventHandler(this.distortionPctrBox_Click);
            // 
            // reverbPctrBox
            // 
            this.reverbPctrBox.Image = ((System.Drawing.Image)(resources.GetObject("reverbPctrBox.Image")));
            this.reverbPctrBox.Location = new System.Drawing.Point(108, 180);
            this.reverbPctrBox.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.reverbPctrBox.Name = "reverbPctrBox";
            this.reverbPctrBox.Size = new System.Drawing.Size(180, 262);
            this.reverbPctrBox.SizeMode = System.Windows.Forms.PictureBoxSizeMode.CenterImage;
            this.reverbPctrBox.TabIndex = 9;
            this.reverbPctrBox.TabStop = false;
            this.reverbPctrBox.Click += new System.EventHandler(this.reverbPctrBox_Click);
            // 
            // chorusPctrBox
            // 
            this.chorusPctrBox.Image = ((System.Drawing.Image)(resources.GetObject("chorusPctrBox.Image")));
            this.chorusPctrBox.Location = new System.Drawing.Point(708, 180);
            this.chorusPctrBox.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.chorusPctrBox.Name = "chorusPctrBox";
            this.chorusPctrBox.Size = new System.Drawing.Size(212, 262);
            this.chorusPctrBox.SizeMode = System.Windows.Forms.PictureBoxSizeMode.CenterImage;
            this.chorusPctrBox.TabIndex = 10;
            this.chorusPctrBox.TabStop = false;
            this.chorusPctrBox.Click += new System.EventHandler(this.chorusPctrBox_Click);
            // 
            // chorusEnBtn
            // 
            this.chorusEnBtn.BackColor = System.Drawing.Color.Transparent;
            this.chorusEnBtn.BackgroundImage = ((System.Drawing.Image)(resources.GetObject("chorusEnBtn.BackgroundImage")));
            this.chorusEnBtn.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.chorusEnBtn.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.chorusEnBtn.Location = new System.Drawing.Point(761, 345);
            this.chorusEnBtn.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.chorusEnBtn.Name = "chorusEnBtn";
            this.chorusEnBtn.Size = new System.Drawing.Size(107, 72);
            this.chorusEnBtn.TabIndex = 11;
            this.chorusEnBtn.Text = "OFF";
            this.chorusEnBtn.UseVisualStyleBackColor = false;
            this.chorusEnBtn.Click += new System.EventHandler(this.chorusEnBtn_Click);
            // 
            // label2
            // 
            this.label2.AutoSize = true;
            this.label2.Font = new System.Drawing.Font("Candara Light", 18F, System.Drawing.FontStyle.Italic, System.Drawing.GraphicsUnit.Point);
            this.label2.ForeColor = System.Drawing.Color.White;
            this.label2.Location = new System.Drawing.Point(137, 131);
            this.label2.Name = "label2";
            this.label2.Size = new System.Drawing.Size(121, 44);
            this.label2.TabIndex = 12;
            this.label2.Text = "Reverb";
            // 
            // label3
            // 
            this.label3.AutoSize = true;
            this.label3.Font = new System.Drawing.Font("Candara Light", 18F, System.Drawing.FontStyle.Italic, System.Drawing.GraphicsUnit.Point);
            this.label3.ForeColor = System.Drawing.Color.White;
            this.label3.Location = new System.Drawing.Point(355, 131);
            this.label3.Name = "label3";
            this.label3.Size = new System.Drawing.Size(89, 44);
            this.label3.TabIndex = 13;
            this.label3.Text = "Echo";
            // 
            // label4
            // 
            this.label4.AutoSize = true;
            this.label4.Font = new System.Drawing.Font("Candara Light", 18F, System.Drawing.FontStyle.Italic, System.Drawing.GraphicsUnit.Point);
            this.label4.ForeColor = System.Drawing.Color.White;
            this.label4.Location = new System.Drawing.Point(531, 131);
            this.label4.Name = "label4";
            this.label4.Size = new System.Drawing.Size(141, 44);
            this.label4.TabIndex = 14;
            this.label4.Text = "Tremolo";
            // 
            // label5
            // 
            this.label5.AutoSize = true;
            this.label5.Font = new System.Drawing.Font("Candara Light", 18F, System.Drawing.FontStyle.Italic, System.Drawing.GraphicsUnit.Point);
            this.label5.ForeColor = System.Drawing.Color.White;
            this.label5.Location = new System.Drawing.Point(756, 131);
            this.label5.Name = "label5";
            this.label5.Size = new System.Drawing.Size(120, 44);
            this.label5.TabIndex = 15;
            this.label5.Text = "Chorus";
            // 
            // label6
            // 
            this.label6.AutoSize = true;
            this.label6.Font = new System.Drawing.Font("Candara Light", 18F, System.Drawing.FontStyle.Italic, System.Drawing.GraphicsUnit.Point);
            this.label6.ForeColor = System.Drawing.Color.White;
            this.label6.Location = new System.Drawing.Point(953, 131);
            this.label6.Name = "label6";
            this.label6.Size = new System.Drawing.Size(168, 44);
            this.label6.TabIndex = 16;
            this.label6.Text = "Distortion";
            // 
            // label7
            // 
            this.label7.AutoSize = true;
            this.label7.Font = new System.Drawing.Font("Candara Light", 18F, System.Drawing.FontStyle.Italic, System.Drawing.GraphicsUnit.Point);
            this.label7.ForeColor = System.Drawing.Color.White;
            this.label7.Location = new System.Drawing.Point(1164, 131);
            this.label7.Name = "label7";
            this.label7.Size = new System.Drawing.Size(163, 44);
            this.label7.TabIndex = 17;
            this.label7.Text = "Overdrive";
            // 
            // distEnBtn
            // 
            this.distEnBtn.BackColor = System.Drawing.Color.Transparent;
            this.distEnBtn.BackgroundImage = ((System.Drawing.Image)(resources.GetObject("distEnBtn.BackgroundImage")));
            this.distEnBtn.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.distEnBtn.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.distEnBtn.Location = new System.Drawing.Point(978, 360);
            this.distEnBtn.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.distEnBtn.Name = "distEnBtn";
            this.distEnBtn.Size = new System.Drawing.Size(114, 57);
            this.distEnBtn.TabIndex = 18;
            this.distEnBtn.Text = "OFF";
            this.distEnBtn.UseVisualStyleBackColor = false;
            this.distEnBtn.Click += new System.EventHandler(this.distEnBtn_Click);
            // 
            // reverbEnBtn
            // 
            this.reverbEnBtn.BackColor = System.Drawing.Color.Transparent;
            this.reverbEnBtn.BackgroundImage = ((System.Drawing.Image)(resources.GetObject("reverbEnBtn.BackgroundImage")));
            this.reverbEnBtn.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.reverbEnBtn.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Bold, System.Drawing.GraphicsUnit.Point);
            this.reverbEnBtn.Location = new System.Drawing.Point(148, 358);
            this.reverbEnBtn.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.reverbEnBtn.Name = "reverbEnBtn";
            this.reverbEnBtn.Size = new System.Drawing.Size(100, 42);
            this.reverbEnBtn.TabIndex = 19;
            this.reverbEnBtn.Text = "OFF";
            this.reverbEnBtn.UseVisualStyleBackColor = false;
            this.reverbEnBtn.Click += new System.EventHandler(this.reverbEnBtn_Click);
            // 
            // EffectsForm
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(10F, 25F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(35)))), ((int)(((byte)(35)))), ((int)(((byte)(50)))));
            this.ClientSize = new System.Drawing.Size(1789, 1050);
            this.Controls.Add(this.reverbEnBtn);
            this.Controls.Add(this.distEnBtn);
            this.Controls.Add(this.label7);
            this.Controls.Add(this.label6);
            this.Controls.Add(this.label5);
            this.Controls.Add(this.label4);
            this.Controls.Add(this.label3);
            this.Controls.Add(this.label2);
            this.Controls.Add(this.chorusEnBtn);
            this.Controls.Add(this.chorusPctrBox);
            this.Controls.Add(this.reverbPctrBox);
            this.Controls.Add(this.distortionPctrBox);
            this.Controls.Add(this.label1);
            this.Controls.Add(this.echoEnBtn);
            this.Controls.Add(this.tremoloEnBtn);
            this.Controls.Add(this.odEnableBtn);
            this.Controls.Add(this.parametersPanel);
            this.Controls.Add(this.delayPctrBox);
            this.Controls.Add(this.tremoloPctrBox);
            this.Controls.Add(this.overdrivePctrBox);
            this.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.Name = "EffectsForm";
            this.Text = "Effects";
            this.FormClosing += new System.Windows.Forms.FormClosingEventHandler(this.EffectsForm_FormClosing);
            ((System.ComponentModel.ISupportInitialize)(this.overdrivePctrBox)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.tremoloPctrBox)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.delayPctrBox)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.distortionPctrBox)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.reverbPctrBox)).EndInit();
            ((System.ComponentModel.ISupportInitialize)(this.chorusPctrBox)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.PictureBox overdrivePctrBox;
        private System.Windows.Forms.PictureBox tremoloPctrBox;
        private System.Windows.Forms.PictureBox delayPctrBox;
        private System.Windows.Forms.Panel parametersPanel;
        private System.Windows.Forms.Button odEnableBtn;
        private System.Windows.Forms.Button tremoloEnBtn;
        private System.Windows.Forms.Button echoEnBtn;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.PictureBox distortionPctrBox;
        private System.Windows.Forms.PictureBox reverbPctrBox;
        private System.Windows.Forms.PictureBox chorusPctrBox;
        private System.Windows.Forms.Button chorusEnBtn;
        private System.Windows.Forms.Label label2;
        private System.Windows.Forms.Label label3;
        private System.Windows.Forms.Label label4;
        private System.Windows.Forms.Label label5;
        private System.Windows.Forms.Label label6;
        private System.Windows.Forms.Label label7;
        private System.Windows.Forms.Button distEnBtn;
        private System.Windows.Forms.Button reverbEnBtn;
    }
}