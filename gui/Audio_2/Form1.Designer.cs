
namespace Audio_2
{
    partial class Form1
    {
        /// <summary>
        ///  Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        ///  Clean up any resources being used.
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
        ///  Required method for Designer support - do not modify
        ///  the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            System.ComponentModel.ComponentResourceManager resources = new System.ComponentModel.ComponentResourceManager(typeof(Form1));
            this.SideMenuPanel = new System.Windows.Forms.Panel();
            this.SettingsBtn = new FontAwesome.Sharp.IconButton();
            this.EffectMenuBtn = new FontAwesome.Sharp.IconButton();
            this.LogoPanel = new System.Windows.Forms.Panel();
            this.LogoPictureBox = new System.Windows.Forms.PictureBox();
            this.panelChildForm = new System.Windows.Forms.Panel();
            this.shadowPanel = new System.Windows.Forms.Panel();
            this.SideMenuPanel.SuspendLayout();
            this.LogoPanel.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.LogoPictureBox)).BeginInit();
            this.SuspendLayout();
            // 
            // SideMenuPanel
            // 
            this.SideMenuPanel.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(35)))), ((int)(((byte)(35)))), ((int)(((byte)(50)))));
            this.SideMenuPanel.Controls.Add(this.SettingsBtn);
            this.SideMenuPanel.Controls.Add(this.EffectMenuBtn);
            this.SideMenuPanel.Controls.Add(this.LogoPanel);
            this.SideMenuPanel.Dock = System.Windows.Forms.DockStyle.Left;
            this.SideMenuPanel.Location = new System.Drawing.Point(0, 0);
            this.SideMenuPanel.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.SideMenuPanel.Name = "SideMenuPanel";
            this.SideMenuPanel.Size = new System.Drawing.Size(357, 1050);
            this.SideMenuPanel.TabIndex = 1;
            // 
            // SettingsBtn
            // 
            this.SettingsBtn.Dock = System.Windows.Forms.DockStyle.Top;
            this.SettingsBtn.FlatAppearance.BorderSize = 0;
            this.SettingsBtn.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.SettingsBtn.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point);
            this.SettingsBtn.ForeColor = System.Drawing.Color.Gainsboro;
            this.SettingsBtn.IconChar = FontAwesome.Sharp.IconChar.Cog;
            this.SettingsBtn.IconColor = System.Drawing.Color.Gainsboro;
            this.SettingsBtn.IconFont = FontAwesome.Sharp.IconFont.Auto;
            this.SettingsBtn.IconSize = 52;
            this.SettingsBtn.ImageAlign = System.Drawing.ContentAlignment.MiddleLeft;
            this.SettingsBtn.Location = new System.Drawing.Point(0, 384);
            this.SettingsBtn.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.SettingsBtn.Name = "SettingsBtn";
            this.SettingsBtn.Padding = new System.Windows.Forms.Padding(29, 0, 29, 0);
            this.SettingsBtn.Size = new System.Drawing.Size(357, 117);
            this.SettingsBtn.TabIndex = 2;
            this.SettingsBtn.Text = "Settings";
            this.SettingsBtn.TextAlign = System.Drawing.ContentAlignment.MiddleLeft;
            this.SettingsBtn.TextImageRelation = System.Windows.Forms.TextImageRelation.ImageBeforeText;
            this.SettingsBtn.UseVisualStyleBackColor = true;
            this.SettingsBtn.Click += new System.EventHandler(this.SettingsBtn_Click);
            // 
            // EffectMenuBtn
            // 
            this.EffectMenuBtn.Dock = System.Windows.Forms.DockStyle.Top;
            this.EffectMenuBtn.FlatAppearance.BorderSize = 0;
            this.EffectMenuBtn.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.EffectMenuBtn.Font = new System.Drawing.Font("Segoe UI", 14F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point);
            this.EffectMenuBtn.ForeColor = System.Drawing.Color.Gainsboro;
            this.EffectMenuBtn.IconChar = FontAwesome.Sharp.IconChar.SlidersH;
            this.EffectMenuBtn.IconColor = System.Drawing.Color.Gainsboro;
            this.EffectMenuBtn.IconFont = FontAwesome.Sharp.IconFont.Auto;
            this.EffectMenuBtn.IconSize = 52;
            this.EffectMenuBtn.ImageAlign = System.Drawing.ContentAlignment.MiddleLeft;
            this.EffectMenuBtn.Location = new System.Drawing.Point(0, 267);
            this.EffectMenuBtn.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.EffectMenuBtn.Name = "EffectMenuBtn";
            this.EffectMenuBtn.Padding = new System.Windows.Forms.Padding(29, 0, 29, 0);
            this.EffectMenuBtn.Size = new System.Drawing.Size(357, 117);
            this.EffectMenuBtn.TabIndex = 1;
            this.EffectMenuBtn.Text = "Effects Menu";
            this.EffectMenuBtn.TextAlign = System.Drawing.ContentAlignment.MiddleLeft;
            this.EffectMenuBtn.TextImageRelation = System.Windows.Forms.TextImageRelation.ImageBeforeText;
            this.EffectMenuBtn.UseVisualStyleBackColor = true;
            this.EffectMenuBtn.Click += new System.EventHandler(this.EffectMenuBtn_Click);
            // 
            // LogoPanel
            // 
            this.LogoPanel.Controls.Add(this.LogoPictureBox);
            this.LogoPanel.Dock = System.Windows.Forms.DockStyle.Top;
            this.LogoPanel.Location = new System.Drawing.Point(0, 0);
            this.LogoPanel.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.LogoPanel.Name = "LogoPanel";
            this.LogoPanel.Size = new System.Drawing.Size(357, 267);
            this.LogoPanel.TabIndex = 0;
            // 
            // LogoPictureBox
            // 
            this.LogoPictureBox.Image = ((System.Drawing.Image)(resources.GetObject("LogoPictureBox.Image")));
            this.LogoPictureBox.Location = new System.Drawing.Point(17, 20);
            this.LogoPictureBox.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.LogoPictureBox.Name = "LogoPictureBox";
            this.LogoPictureBox.Size = new System.Drawing.Size(314, 237);
            this.LogoPictureBox.SizeMode = System.Windows.Forms.PictureBoxSizeMode.Zoom;
            this.LogoPictureBox.TabIndex = 0;
            this.LogoPictureBox.TabStop = false;
            // 
            // panelChildForm
            // 
            this.panelChildForm.Dock = System.Windows.Forms.DockStyle.Fill;
            this.panelChildForm.Location = new System.Drawing.Point(357, 0);
            this.panelChildForm.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.panelChildForm.Name = "panelChildForm";
            this.panelChildForm.Size = new System.Drawing.Size(1526, 1050);
            this.panelChildForm.TabIndex = 2;
            // 
            // shadowPanel
            // 
            this.shadowPanel.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(60)))), ((int)(((byte)(60)))), ((int)(((byte)(90)))));
            this.shadowPanel.Dock = System.Windows.Forms.DockStyle.Left;
            this.shadowPanel.Location = new System.Drawing.Point(357, 0);
            this.shadowPanel.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.shadowPanel.Name = "shadowPanel";
            this.shadowPanel.Size = new System.Drawing.Size(4, 1050);
            this.shadowPanel.TabIndex = 3;
            // 
            // Form1
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(10F, 25F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.White;
            this.ClientSize = new System.Drawing.Size(1883, 1050);
            this.Controls.Add(this.shadowPanel);
            this.Controls.Add(this.panelChildForm);
            this.Controls.Add(this.SideMenuPanel);
            this.Icon = ((System.Drawing.Icon)(resources.GetObject("$this.Icon")));
            this.Margin = new System.Windows.Forms.Padding(4, 5, 4, 5);
            this.Name = "Form1";
            this.Text = "Guitar Multi-Effect";
            this.FormClosing += new System.Windows.Forms.FormClosingEventHandler(this.Form1_FormClosing);
            this.Load += new System.EventHandler(this.Form1_Load);
            this.SideMenuPanel.ResumeLayout(false);
            this.LogoPanel.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)(this.LogoPictureBox)).EndInit();
            this.ResumeLayout(false);

        }

        #endregion
        private System.Windows.Forms.Panel SideMenuPanel;
        private FontAwesome.Sharp.IconButton SettingsBtn;
        private FontAwesome.Sharp.IconButton EffectMenuBtn;
        private System.Windows.Forms.Panel LogoPanel;
        private System.Windows.Forms.PictureBox LogoPictureBox;
        private System.Windows.Forms.Panel panelChildForm;
        private System.Windows.Forms.Panel shadowPanel;
    }
}

