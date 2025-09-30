import tkinter as tk
from tkinter import messagebox, ttk
import subprocess
import threading
import time
import webbrowser
import os
import sys
import json # Added for potential future use

class AyoFokusLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("📚 Ayo Fokus - Launcher")
        self.root.geometry("550x450") # Slightly larger window
        self.root.configure(bg="#f0f4f8")
        self.root.resizable(False, False)
        
        # Server process
        self.server_process = None
        self.server_running = False
        
        self.setup_ui()
        self.center_window()
        
    def setup_ui(self):
        """Setup the launcher UI"""
        # Title Bar
        title_frame = tk.Frame(self.root, bg="#667eea", height=90)
        title_frame.pack(fill=tk.X)
        title_frame.pack_propagate(False)
        
        tk.Label(
            title_frame,
            text="📚 Ayo Fokus",
            font=("Segoe UI", 24, "bold"),
            fg="white",
            bg="#667eea"
        ).pack(pady=(10, 0))
        
        tk.Label(
            title_frame,
            text="Sistem Monitoring Kelas Online",
            font=("Segoe UI", 11),
            fg="#e8eaff",
            bg="#667eea"
        ).pack()
        
        # Main content area
        main_frame = tk.Frame(self.root, bg="#f0f4f8", padx=30, pady=25)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Status section
        status_frame = tk.LabelFrame(
            main_frame,
            text="Status Server",
            font=("Segoe UI", 13, "bold"),
            bg="#f0f4f8",
            fg="#333",
            bd=2, relief=tk.GROOVE # Added border for modern look
        )
        status_frame.pack(fill=tk.X, pady=(0, 25))
        
        self.status_label = tk.Label(
            status_frame,
            text="🔴 Server Tidak Aktif",
            font=("Segoe UI", 12, "bold"),
            bg="#f0f4f8",
            fg="#dc3545",
            pady=12
        )
        self.status_label.pack()
        
        # Server controls
        server_frame = tk.LabelFrame(
            main_frame,
            text="Kontrol Server",
            font=("Segoe UI", 13, "bold"),
            bg="#f0f4f8",
            fg="#333",
            bd=2, relief=tk.GROOVE
        )
        server_frame.pack(fill=tk.X, pady=(0, 25))
        
        btn_frame1 = tk.Frame(server_frame, bg="#f0f4f8")
        btn_frame1.pack(pady=12)
        
        self.start_btn = tk.Button(
            btn_frame1,
            text="🚀 Mulai Server",
            command=self.start_server,
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=25,
            pady=10,
            border=0,
            cursor="hand2",
            relief=tk.FLAT, # Flat design
            activebackground="#218838", activeforeground="white"
        )
        self.start_btn.pack(side=tk.LEFT, padx=8)
        
        self.stop_btn = tk.Button(
            btn_frame1,
            text="⏹️ Stop Server",
            command=self.stop_server,
            bg="#dc3545",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=25,
            pady=10,
            border=0,
            state=tk.DISABLED,
            cursor="hand2",
            relief=tk.FLAT,
            activebackground="#c82333", activeforeground="white"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=8)
        
        # Application access
        app_frame = tk.LabelFrame(
            main_frame,
            text="Akses Aplikasi",
            font=("Segoe UI", 13, "bold"),
            bg="#f0f4f8",
            fg="#333",
            bd=2, relief=tk.GROOVE
        )
        app_frame.pack(fill=tk.X, pady=(0, 25))
        
        btn_frame2 = tk.Frame(app_frame, bg="#f0f4f8")
        btn_frame2.pack(pady=12)
        
        self.web_btn = tk.Button(
            btn_frame2,
            text="🌐 Buka Web App",
            command=self.open_web_app,
            bg="#007bff",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=25,
            pady=10,
            border=0,
            state=tk.DISABLED,
            cursor="hand2",
            relief=tk.FLAT,
            activebackground="#0069d9", activeforeground="white"
        )
        self.web_btn.pack(side=tk.LEFT, padx=8)
        
        self.monitoring_btn = tk.Button(
            btn_frame2,
            text="🖥️ Monitoring Desktop",
            command=self.open_monitoring,
            bg="#6f42c1",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=25,
            pady=10,
            border=0,
            cursor="hand2",
            relief=tk.FLAT,
            activebackground="#5a32a3", activeforeground="white"
        )
        self.monitoring_btn.pack(side=tk.LEFT, padx=8)
        
        # Information
        info_frame = tk.LabelFrame(
            main_frame,
            text="Informasi",
            font=("Segoe UI", 13, "bold"),
            bg="#f0f4f8",
            fg="#333",
            bd=2, relief=tk.GROOVE
        )
        info_frame.pack(fill=tk.X)
        
        info_text = tk.Text(
            info_frame,
            height=4,
            bg="#f8f9fa",
            fg="#495057",
            font=("Segoe UI", 9),
            wrap=tk.WORD,
            border=0,
            padx=10,
            pady=8
        )
        info_text.pack(fill=tk.X, padx=5, pady=5)
        
        info_content = """• Server akan berjalan di http://localhost:5000
- Pastikan port 5000 tidak digunakan aplikasi lain
- Monitoring desktop dapat dijalankan terpisah
- Tutup launcher ini akan menghentikan server"""
        
        info_text.insert("1.0", info_content)
        info_text.config(state=tk.DISABLED)
        
        # Progress bar (hidden initially)
        self.progress = ttk.Progressbar(
            self.root, # Placed outside main_frame for better visibility
            mode='indeterminate',
            length=400,
            style="TProgressbar" # Custom style
        )
        style = ttk.Style()
        style.theme_use('clam') # Use 'clam' theme for better styling control
        style.configure("TProgressbar",
                        troughcolor='#e0e0e0',
                        background='#667eea',
                        thickness=10)
    
    def center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (self.root.winfo_width() // 2)
        y = (self.root.winfo_screenheight() // 2) - (self.root.winfo_height() // 2)
        self.root.geometry(f"+{x}+{y}")
    
    def start_server(self):
        """Start the Flask server"""
        try:
            # Show progress
            self.progress.pack(pady=15)
            self.progress.start(15) # Faster animation
            
            # Update UI
            self.start_btn.config(state=tk.DISABLED, text="⏳ Memulai...")
            self.status_label.config(text="🟡 Memulai Server...", fg="#ffc107")
            
            # Start server in background thread
            def start_server_thread():
                try:
                    # Check if app.py exists
                    if not os.path.exists("app.py"):
                        self.root.after(0, lambda: self.show_error("File app.py tidak ditemukan!"))
                        return
                    
                    # Run database migration first
                    self.root.after(0, lambda: self.status_label.config(text="🟡 Menjalankan Migrasi DB...", fg="#ffc107"))
                    migration_success = self.run_migration_script()
                    if not migration_success:
                        self.root.after(0, lambda: self.show_error("Migrasi database gagal. Periksa konsol untuk detail."))
                        return

                    self.root.after(0, lambda: self.status_label.config(text="🟡 Memulai Server...", fg="#ffc107"))
                    
                    # Start server process
                    # Use sys.executable to ensure correct python interpreter
                    # Use -u for unbuffered output, helpful for debugging
                    self.server_process = subprocess.Popen(
                        [sys.executable, "-u", "app.py"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                        text=True # Decode stdout/stderr as text
                    )
                    
                    # Read stdout to detect server start (more robust)
                    server_started_line = "=== Ayo Fokus Backend Started ==="
                    server_output = []
                    start_time = time.time()
                    timeout = 30 # seconds to wait for server to start
                    
                    while time.time() - start_time < timeout:
                        line = self.server_process.stdout.readline()
                        if line:
                            server_output.append(line.strip())
                            print(f"[SERVER]: {line.strip()}") # Log server output to console
                            if server_started_line in line:
                                self.server_running = True
                                self.root.after(0, self.on_server_started)
                                return # Exit thread
                        elif self.server_process.poll() is not None: # Server exited prematurely
                            break
                        time.sleep(0.1) # Small delay to prevent busy-waiting

                    # If loop finishes without finding the line or server exited
                    if not self.server_running:
                        stderr_output = self.server_process.stderr.read()
                        full_output = "\n".join(server_output) + "\n" + stderr_output
                        error_msg = f"Server gagal dimulai dalam {timeout} detik.\nOutput server:\n{full_output}"
                        self.root.after(0, lambda: self.show_error(error_msg))
                        self.server_process.kill() # Ensure it's stopped
                        self.server_process = None
                        
                except Exception as e:
                    self.root.after(0, lambda: self.show_error(f"Error memulai server: {str(e)}"))
            
            threading.Thread(target=start_server_thread, daemon=True).start()
            
        except Exception as e:
            self.show_error(f"Error: {str(e)}")
    
    def run_migration_script(self):
        """Execute the database migration script."""
        try:
            migration_process = subprocess.run(
                [sys.executable, "database_migration.py"],
                capture_output=True,
                text=True,
                check=True # Raise CalledProcessError for non-zero exit codes
            )
            print("--- Database Migration Output ---")
            print(migration_process.stdout)
            if migration_process.stderr:
                print("--- Database Migration Errors ---")
                print(migration_process.stderr)
            print("--- End Migration Output ---")
            return True
        except subprocess.CalledProcessError as e:
            print(f"--- Database Migration Failed ---")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            print(f"--- End Migration Failure ---")
            return False
        except Exception as e:
            print(f"Error running migration script: {e}")
            return False

    def on_server_started(self):
        """Called when server successfully starts"""
        # Hide progress
        self.progress.stop()
        self.progress.pack_forget()
        
        # Update UI
        self.status_label.config(text="🟢 Server Aktif", fg="#28a745")
        self.start_btn.config(state=tk.DISABLED, text="🚀 Mulai Server")
        self.stop_btn.config(state=tk.NORMAL)
        self.web_btn.config(state=tk.NORMAL)
        
        # Show success message
        messagebox.showinfo(
            "Sukses",
            "Server berhasil dimulai!\n\nAnda dapat mengakses aplikasi web atau monitoring desktop."
        )
    
    def stop_server(self):
        """Stop the Flask server"""
        if self.server_process and self.server_running:
            try:
                # Attempt graceful termination first
                self.server_process.terminate()
                self.server_process.wait(timeout=5) # Wait for 5 seconds
            except subprocess.TimeoutExpired:
                # If not terminated, force kill
                self.server_process.kill()
                self.server_process.wait() # Wait for it to be killed
            except Exception as e:
                print(f"Error stopping server: {e}")
            
            self.server_process = None
            self.server_running = False
            
            # Update UI
            self.status_label.config(text="🔴 Server Tidak Aktif", fg="#dc3545")
            self.start_btn.config(state=tk.NORMAL)
            self.stop_btn.config(state=tk.DISABLED)
            self.web_btn.config(state=tk.DISABLED)
            
            messagebox.showinfo("Info", "Server telah dihentikan.")
    
    def open_web_app(self):
        """Open web application in browser"""
        if self.server_running:
            webbrowser.open("http://localhost:5000")
        else:
            messagebox.showwarning("Peringatan", "Server belum berjalan!")
    
    def open_monitoring(self):
        """Open desktop monitoring application"""
        try:
            if not os.path.exists("monitoring.py"):
                messagebox.showerror("Error", "File monitoring.py tidak ditemukan!")
                return
            
            # Read user data from localStorage simulation (if any)
            # This is a simplified approach. In a real app, you'd have a more robust way
            # to pass user/class info or have the desktop app handle its own login.
            # For this demo, we'll just launch it.
            
            subprocess.Popen([sys.executable, "monitoring.py"])
            messagebox.showinfo("Info", "Aplikasi monitoring desktop telah dibuka.\n\nCatatan: Untuk sinkronisasi, Anda perlu login di web app terlebih dahulu dan mengatur Class ID serta Token di monitoring.py (atau melalui UI-nya jika ada).")
            
        except Exception as e:
            messagebox.showerror("Error", f"Gagal membuka monitoring desktop: {str(e)}")
    
    def show_error(self, message):
        """Show error message and reset UI"""
        # Hide progress
        self.progress.stop()
        self.progress.pack_forget()
        
        # Reset UI
        self.status_label.config(text="🔴 Server Tidak Aktif", fg="#dc3545")
        self.start_btn.config(state=tk.NORMAL, text="🚀 Mulai Server")
        self.stop_btn.config(state=tk.DISABLED)
        self.web_btn.config(state=tk.DISABLED)
        
        # Show error
        messagebox.showerror("Error", message)
    
    def on_closing(self):
        """Handle window closing"""
        if self.server_process and self.server_running:
            if messagebox.askokcancel(
                "Konfirmasi",
                "Server masih berjalan. Menutup launcher akan menghentikan server.\n\nLanjutkan?"
            ):
                self.stop_server()
                self.root.destroy()
        else:
            self.root.destroy()
    
    def run(self):
        """Start the launcher"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Add hover effects (more subtle for flat buttons)
        def on_enter(event):
            event.widget.config(relief=tk.RAISED)
        
        def on_leave(event):
            event.widget.config(relief=tk.FLAT)
        
        for widget in [self.start_btn, self.stop_btn, self.web_btn, self.monitoring_btn]:
            widget.bind("<Enter>", on_enter)
            widget.bind("<Leave>", on_leave)
        
        self.root.mainloop()

if __name__ == "__main__":
    # Check required files
    required_files = ["app.py", "index.html", "monitoring.py", "requirements.txt", "database_migration.py"]
    missing_files = [f for f in required_files if not os.path.exists(f)]
    
    if missing_files:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "File Tidak Ditemukan",
            f"File berikut tidak ditemukan:\n" + "\n".join(f"• {f}" for f in missing_files) +
            "\n\nPastikan semua file aplikasi ada di folder yang sama dengan launcher.py"
        )
        sys.exit(1)
    
    launcher = AyoFokusLauncher()
    launcher.run()