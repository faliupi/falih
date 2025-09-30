import time
import tkinter as tk
from tkinter import messagebox, simpledialog
import threading
import platform
import os
import uuid
import requests
import datetime
import logging
import sys # Import sys to read command line arguments

# Setup logging for monitoring.py
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Import modul khusus Windows jika tersedia
try:
    import win32gui
    import win32con
    import win32api
    import win32process
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    logging.warning("win32gui, win32con, win32api, win32process modules not found. Window detection will be limited on Windows.")

# Import untuk suara notifikasi cross-platform
try:
    if platform.system() == "Windows":
        import winsound
    else:
        pass # Placeholder for non-Windows sound libraries
except ImportError:
    logging.warning("winsound module not found. Winsound module not found. Sound notifications may not work on Windows.")


class MonitoringApp:
    def __init__(self, class_id=None, user_token=None, class_name=None, user_id=None):
        self.monitoring_active = False
        self.current_class_id = class_id
        self.user_token = user_token
        self.user_id = user_id
        self.in_meet = False # Status apakah aplikasi meet/browser aktif
        self.popup_active = False
        self.popup_dismissed = False # Flag untuk menandai apakah popup sudah di-dismiss oleh user
        self.warning_count = 0
        self.popup_window = None
        self.popup_scheduled = False
        self.last_window_check = ""
        self.session_id = f"desktop_{uuid.uuid4().hex[:8]}_{int(time.time())}" # Generate unique session ID
        self.heartbeat_thread = None
        self.heartbeat_active = False
        self.popup_timer_id = None # Untuk membatalkan timer popup
        self.blur_timer_id = None # Untuk membatalkan timer blur
        self.class_name = class_name if class_name else "Tidak ada" # Default class name
        self.monitor_thread = None # Added to keep track of the monitor loop thread
        self.last_in_meet_status = None # Untuk mendeteksi perubahan status in_meet

        # API Configuration
        self.api_base = "http://localhost:5000/api"
        self.heartbeat_interval = 3  # seconds (disinkronkan dengan polling frontend)
        self.BLUR_THRESHOLD_MS = 3000 # Waktu (ms) untuk menganggap window blur (3 detik)
        self.WARNING_DELAY_MS = 10000 # Waktu (ms) sebelum popup muncul setelah keluar Meet (10 detik)

        # Initialize GUI
        self.root = tk.Tk()
        self.root.withdraw() # Hide main window initially
        self.root.attributes("-topmost", True) # Keep on top for initial setup (will be set to False later)

        self.setup_ui()

    def setup_ui(self):
        """Setup the monitoring UI"""
        self.root.title("Ayo Fokus - Monitoring Desktop (Real-time Sync)")
        self.root.geometry("480x450") # Slightly larger window
        self.root.configure(bg="#f0f4f8") # Light background

        # Title
        title_label = tk.Label(
            self.root,
            text="📚 Ayo Fokus - Real-time Monitor",
            font=("Segoe UI", 18, "bold"),
            bg="#f0f4f8",
            fg="#333",
        )
        title_label.pack(pady=15)

        # Status labels
        self.status_label = tk.Label(
            self.root, text="Status: Tidak Aktif", font=("Segoe UI", 13, "bold"), bg="#f0f4f8", fg="#dc3545"
        )
        self.status_label.pack(pady=5)

        self.class_label = tk.Label(
            self.root, text=f"Kelas: {self.class_name}", font=("Segoe UI", 11), bg="#f0f4f8", fg="#666"
        )
        self.class_label.pack(pady=5)

        # Status info frame
        info_frame = tk.Frame(self.root, bg="#f0f4f8")
        info_frame.pack(pady=10, padx=25, fill=tk.X)

        self.meet_status_label = tk.Label(
            info_frame, text="Status Meet: Menunggu...", font=("Segoe UI", 10), bg="#f0f4f8", fg="#666"
        )
        self.meet_status_label.pack(anchor="w")

        self.warning_count_label = tk.Label(
            info_frame, text="Jumlah Peringatan: 0", font=("Segoe UI", 10), bg="#f0f4f8", fg="#666"
        )
        self.warning_count_label.pack(anchor="w")

        self.heartbeat_status_label = tk.Label(
            info_frame, text="Heartbeat: Tidak Aktif", font=("Segoe UI", 10), bg="#f0f4f8", fg="#666"
        )
        self.heartbeat_status_label.pack(anchor="w")

        self.connection_status_label = tk.Label(
            info_frame, text="🔴 Offline", font=("Segoe UI", 10, "bold"), bg="#f0f4f8", fg="#dc3545"
        )
        self.connection_status_label.pack(anchor="w")

        # Log frame
        log_frame = tk.Frame(self.root, bg="#f0f4f8")
        log_frame.pack(pady=15, padx=25, fill=tk.BOTH, expand=True)

        tk.Label(log_frame, text="Log Aktivitas (Real-time Sync):", font=("Segoe UI", 11, "bold"), bg="#f0f4f8").pack(
            anchor="w", pady=(0, 5)
        )

        self.log_text = tk.Text(
            log_frame, height=10, font=("Courier New", 9), bg="white", fg="#333", wrap=tk.WORD,
            bd=1, relief=tk.SOLID # Added border
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # Buttons
        btn_frame = tk.Frame(self.root, bg="#f0f4f8")
        btn_frame.pack(pady=20)

        self.start_btn = tk.Button(
            btn_frame,
            text="▶️ Mulai Monitoring",
            command=self._start_monitoring_logic, # Langsung panggil logika start
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=8,
            bd=0, relief=tk.FLAT, # Flat design
            activebackground="#218838", activeforeground="white",
            cursor="hand2"
        )
        self.start_btn.pack(side=tk.LEFT, padx=8)

        self.stop_btn = tk.Button(
            btn_frame,
            text="⏹️ Stop Monitoring",
            command=self.stop_monitoring,
            bg="#dc3545",
            fg="white",
            font=("Segoe UI", 11, "bold"),
            padx=20,
            pady=8,
            bd=0, relief=tk.FLAT,
            state=tk.DISABLED,
            activebackground="#c82333", activeforeground="white",
            cursor="hand2"
        )
        self.stop_btn.pack(side=tk.LEFT, padx=8)

        # Add hover effects for buttons
        def on_enter(e):
            e.widget.config(relief=tk.RAISED)
        def on_leave(e):
            e.widget.config(relief=tk.FLAT)
        
        for btn in [self.start_btn, self.stop_btn]:
            btn.bind("<Enter>", on_enter)
            btn.bind("<Leave>", on_leave)

        # Initial state check for auto-start
        if self.current_class_id and self.user_token and self.user_id:
            self.root.after(100, self._start_monitoring_logic) # Auto-start after a short delay
            self.start_btn.config(state=tk.DISABLED) # Disable start button if auto-starting
        else:
            self.add_log("Parameter monitoring tidak lengkap. Harap masukkan secara manual atau luncurkan via launcher.")
            self.root.deiconify() # Show window if manual input is needed

    def _start_monitoring_logic(self):
        """Start the monitoring process with real-time sync"""
        if not self.monitoring_active:
            # Jika parameter belum diatur, minta input manual
            if not self.current_class_id or not self.user_token or not self.user_id:
                messagebox.showinfo("Input Diperlukan", "Parameter monitoring tidak ditemukan. Harap masukkan Class ID, User ID, dan User Token.")
                class_id_input = simpledialog.askstring("Input", "Masukkan Class ID:", parent=self.root)
                user_id_input = simpledialog.askstring("Input", "Masukkan User ID:", parent=self.root)
                user_token_input = simpledialog.askstring("Input", "Masukkan User Token:", parent=self.root)
                class_name_input = simpledialog.askstring("Input", "Masukkan Nama Kelas (opsional):", parent=self.root)

                if class_id_input and user_id_input and user_token_input:
                    try:
                        self.current_class_id = int(class_id_input)
                        self.user_id = int(user_id_input)
                        self.user_token = user_token_input
                        self.class_name = class_name_input if class_name_input else "Tidak ada"
                        self.class_label.config(text=f"Kelas: {self.class_name}")
                        self.add_log(f"🔧 Parameter diatur secara manual - Kelas ID {self.current_class_id}, User ID {self.user_id}")
                    except ValueError:
                        messagebox.showerror("Error", "Class ID dan User ID harus berupa angka.")
                        self.add_log("ERROR: Class ID atau User ID bukan angka.")
                        return
                else:
                    messagebox.showerror("Error", "Class ID, User ID, dan User Token tidak boleh kosong.")
                    self.add_log("ERROR: Input manual tidak lengkap.")
                    return

            self.monitoring_active = True
            self.in_meet = False # Assume NOT in meet initially, will be detected by monitor_loop
            self.popup_dismissed = False # Reset flag dismissed when monitoring starts
            self.warning_count = 0
            self.popup_scheduled = False
            # self.session_id = f"desktop_{uuid.uuid4().hex[:8]}_{int(time.time())}" # Session ID sudah di-generate di __init__

            self.status_label.config(text="Status: Monitoring Aktif (Real-time)", fg="#28a745")
            self.meet_status_label.config(text="Status Meet: Menunggu deteksi...")
            self.warning_count_label.config(text="Jumlah Peringatan: 0")
            self.heartbeat_status_label.config(text="Heartbeat: Memulai...", fg="#007bff")
            
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)

            # Start monitoring thread
            # The monitor_loop will now handle both detection and heartbeat sending
            self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.monitor_thread.start()

            # No separate start_heartbeat_system call here, as monitor_loop will handle it
            # self.start_heartbeat_system() # This is now integrated into monitor_loop

            self.add_log("Real-time monitoring dimulai - Sinkronisasi dengan web app")
            self.log_activity("desktop_monitoring_started", '[INFO] Desktop monitoring dimulai dengan real-time sync') # Log initial start
            
            self.root.deiconify() # Show the main window
            self.root.lift()
            self.root.attributes("-topmost", True) # Bring to front
            self.root.attributes("-topmost", False) # Allow other windows to be on top

    # Removed start_heartbeat_system and heartbeat_loop as they are now integrated into monitor_loop
    # def start_heartbeat_system(self):
    #     """Start the heartbeat system for real-time status sync"""
    #     self.heartbeat_active = True
    #     self.heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
    #     self.heartbeat_thread.start()
    #     self.add_log(f"Heartbeat system started (interval: {self.heartbeat_interval}s)")

    # def heartbeat_loop(self):
    #     """Continuous heartbeat to sync status with server"""
    #     while self.heartbeat_active and self.monitoring_active:
    #         try:
    #             self.send_heartbeat()
    #             time.sleep(self.heartbeat_interval)
    #         except Exception as e:
    #             self.add_log(f"[HEARTBEAT ERROR] {str(e)}")
    #             time.sleep(self.heartbeat_interval * 2)  # Retry with longer interval on error

    def send_heartbeat(self):
        """Send enhanced heartbeat with message logging"""
        if not self.current_class_id or not self.user_token or not self.session_id or not self.user_id:
            logging.warning("Cannot send heartbeat: Missing class_id, user_token, user_id, or session_id.")
            return

        try:
            response = requests.post(
                f"{self.api_base}/monitoring/heartbeat",
                json={
                    "student_id": self.user_id, # Kirim student_id secara eksplisit
                    "class_id": self.current_class_id,
                    "is_in_meet": self.in_meet,
                    "session_id": self.session_id,
                    "source": "desktop" # Tambahkan source
                },
                headers={"Authorization": f"Bearer {self.user_token}"},
                timeout=3,
            )
            
            if response.status_code == 200:
                data = response.json()
                self.heartbeat_status_label.config(text="Heartbeat: ✓ Aktif", fg="#28a745")
                self.connection_status_label.config(text="🟢 Online", fg="#28a745")
                
                # Log heartbeat periodically (every 30 seconds to avoid spam)
                if not hasattr(self, '_last_heartbeat_log') or (time.time() - self._last_heartbeat_log > 30):
                    self.add_log(f"[HEARTBEAT SYNC] Status={self.in_meet} -> Server updated: {data.get('status_updated', 'unknown')}")
                    self._last_heartbeat_log = time.time()
            else:
                self.heartbeat_status_label.config(text="Heartbeat: Error", fg="#dc3545")
                self.connection_status_label.config(text="🔴 Error", fg="#dc3545")
                self.add_log(f"[HEARTBEAT ERROR] HTTP {response.status_code} - {response.text}")
                
        except requests.exceptions.RequestException as e:
            self.heartbeat_status_label.config(text="Heartbeat: Offline", fg="#dc3545")
            self.connection_status_label.config(text="🔴 Offline", fg="#dc3545")
            self.add_log(f"[HEARTBEAT ERROR] {str(e)}")

    def stop_monitoring(self):
        """Stop the monitoring process"""
        self.monitoring_active = False
        # self.heartbeat_active = False # No longer needed as heartbeat is part of monitor_loop

        self.status_label.config(text="Status: Tidak Aktif", fg="#dc3545")
        self.meet_status_label.config(text="Status Meet: Menunggu...")
        self.heartbeat_status_label.config(text="Heartbeat: Tidak Aktif", fg="#666")
        self.connection_status_label.config(text="🔴 Offline", fg="#dc3545")
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)

        if self.popup_window and self.popup_window.winfo_exists():
            self.close_popup(self.popup_window)
        
        # Cancel popup timer if active
        if self.popup_timer_id:
            self.root.after_cancel(self.popup_timer_id)
            self.popup_timer_id = None
        
        # Cancel blur timer if active
        if self.blur_timer_id:
            self.root.after_cancel(self.blur_timer_id)
            self.blur_timer_id = None

        self.add_log("Real-time monitoring dihentikan")
        self.log_activity("desktop_monitoring_stopped", '[INFO] Desktop monitoring dihentikan') # Log stop event
        self.root.withdraw() # Hide the main window

    def get_active_window_title(self):
        """Get the title of the active window."""
        if platform.system() == "Windows" and WINDOWS_AVAILABLE:
            try:
                hwnd = win32gui.GetForegroundWindow()
                title = win32gui.GetWindowText(hwnd)
                return title.lower()
            except Exception as e:
                logging.error(f"Error getting window title on Windows: {e}")
                return ""
        elif platform.system() == "Darwin": # macOS
            # macOS window title detection is more complex, often requires third-party tools or AppleScript
            # For simplicity, we'll return a placeholder or rely on browser detection if possible
            return "macos_active_window"
        else: # Linux
            # Linux window title detection often requires xprop or similar tools
            # For simplicity, we'll return a placeholder
            return "linux_active_window"

    def detect_meet_status(self):
        """
        Detects if the active window is a Google Meet session.
        Updates self.in_meet accordingly.
        """
        try:
            window_title = self.get_active_window_title() or ""
            title = window_title.lower()

            # Deteksi Google Meet (di Chrome/Edge/Firefox)
            # Memperluas deteksi untuk mencakup "zoom meeting" dan "microsoft teams"
            if (
                "meet.google.com" in title or
                "google meet" in title or
                "zoom meeting" in title or
                "microsoft teams" in title or
                ("google chrome" in title and ("meet.google.com" in title or "google meet" in title)) or
                ("mozilla firefox" in title and ("meet.google.com" in title or "google meet" in title)) or
                ("microsoft edge" in title and ("meet.google.com" in title or "google meet" in title))
            ):
                self.in_meet = True
            else:
                self.in_meet = False

        except Exception as e:
            logging.error(f"Detection error in detect_meet_status: {e}")
            self.in_meet = False # Assume not in meet on error

    def monitor_loop(self):
        """Main monitoring loop with enhanced message consistency and integrated heartbeat."""
        
        while self.monitoring_active:
            try:
                # 1. Detect Meet status
                self.detect_meet_status()
                
                # Update UI label for Meet status
                if self.in_meet:
                    self.meet_status_label.config(text="Status Meet: Ya")
                else:
                    self.meet_status_label.config(text="Status Meet: Tidak")

                # Log window title if changed
                current_title = self.get_active_window_title()
                if current_title != self.last_window_check:
                    self.add_log(f"[DEBUG] Active Window: '{current_title[:50]}...' " if len(current_title) > 50 else f"[DEBUG] Active Window: '{current_title}'")
                    self.last_window_check = current_title

                # 2. Send heartbeat with current status
                self.send_heartbeat()

                # 3. Handle popup logic based on self.in_meet
                # This logic is now simplified as heartbeat handles the primary status sync
                # The popup logic here is for the desktop app's *own* popup, not the web app's.
                if not self.in_meet and not self.popup_active and not self.popup_scheduled and not self.popup_dismissed:
                    # User left Meet/Browser. Schedule popup after WARNING_DELAY_MS.
                    self.popup_scheduled = True
                    self.add_log(f"[DEBUG] Popup dijadwalkan dalam {self.WARNING_DELAY_MS/1000} detik (Desktop sync)")
                    self.popup_timer_id = self.root.after(self.WARNING_DELAY_MS, self.show_warning_popup)
                elif self.in_meet and (self.popup_active or self.popup_scheduled):
                    # User returned to Meet. Cancel any pending popups.
                    if self.popup_timer_id:
                        self.root.after_cancel(self.popup_timer_id)
                        self.popup_timer_id = None
                    if self.popup_window and self.popup_window.winfo_exists():
                        self.close_popup(self.popup_window)
                    self.popup_scheduled = False
                    self.popup_dismissed = False # Reset dismissed flag when back in meet
                    self.add_log("[DEBUG] Kembali ke Meet, popup dibatalkan/ditutup (Desktop)")

                time.sleep(self.heartbeat_interval) # Use heartbeat interval for main loop sleep
                
            except Exception as e:
                self.add_log(f"[ERROR] Monitor loop: {str(e)}")
                time.sleep(self.heartbeat_interval * 2) # Retry with longer interval on error

    # Removed _process_blur_timeout and get_active_window_title_contains_meet
    # as the detection and popup logic is now integrated directly into monitor_loop
    # and relies on the immediate self.in_meet status.

    def show_warning_popup(self):
        """Show warning popup synchronized with web app"""
        self.add_log("DEBUG: show_warning_popup() dipanggil - Real-time sync")
        self.popup_scheduled = False # Reset scheduled flag
        self.popup_timer_id = None # Reset timer ID

        # IMPORTANT CONDITION: Only show popup if monitoring is active AND NOT in Meet AND popup is not active AND not dismissed
        # Pop up tidak muncul saat berada di google meet
        if (
            self.monitoring_active
            and not self.in_meet # Only show if currently NOT in meet
            and not self.popup_active # Only show if no popup is currently active
            and not self.popup_dismissed # Only show if user hasn't dismissed it yet for this "out of meet" period
        ):
            self.add_log("DEBUG: Kondisi popup terpenuhi - Membuat popup sinkron dengan web")
            self.create_enhanced_warning_popup()
        else:
            self.add_log(
                f"DEBUG: Real-time sync - Popup dibatalkan: monitoring={self.monitoring_active}, "
                f"in_meet={self.in_meet}, popup_active={self.popup_active}, dismissed={self.popup_dismissed}"
            )

    def create_enhanced_warning_popup(self):
        """Create enhanced warning popup synchronized with web app design"""
        if self.popup_active: # Prevent multiple popups
            return

        self.popup_active = True
        self.popup_start_time = time.time()
        self.warning_count += 1
        
        self.warning_count_label.config(text=f"Jumlah Peringatan: {self.warning_count}")

        # Create popup window with web app styling
        self.popup_window = tk.Toplevel(self.root)
        self.popup_window.title("⚠️ PERHATIAN - Real-time Sync")
        self.popup_window.geometry("400x250")
        self.popup_window.resizable(False, False)
        
        # Enhanced always-on-top settings
        self.popup_window.wm_attributes("-topmost", True)
        self.popup_window.wm_attributes("-toolwindow", True) # Hide from taskbar on Windows
        
        # Windows-specific enhancements to ensure it stays on top and flashes
        if platform.system() == "Windows" and WINDOWS_AVAILABLE:
            hwnd = int(self.popup_window.wm_frame(), 16)
            win32gui.FlashWindow(hwnd, True)

        # Center the popup
        self.popup_window.update_idletasks()
        x = (self.popup_window.winfo_screenwidth() // 2) - (self.popup_window.winfo_width() // 2)
        y = (self.popup_window.winfo_screenheight() // 2) - (self.popup_window.winfo_height() // 2)
        self.popup_window.geometry(f"+{x}+{y}")

        # Styling to match web version exactly
        outer_frame = tk.Frame(self.popup_window, bg="#c51f1a", bd=0)
        outer_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        content_frame = tk.Frame(outer_frame, bg="white", relief=tk.RAISED, bd=2)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Title - exact match with web version
        tk.Label(
            content_frame,
            text="!! PERHATIAN !!",
            font=("Segoe UI", 14, "bold"),
            fg="#8B0000", # Darker maroon
            bg="white",
        ).pack(pady=(15, 10))

        # Message - exact match with web version
        tk.Label(
            content_frame,
            text="Kamu terdeteksi tidak berada di Google Meet.\nHarap segera kembali ke ruang kelas.\n\n(Desktop Monitor - Real-time Sync)",
            font=("Segoe UI", 10),
            fg="#333333",
            bg="white",
            justify=tk.CENTER,
        ).pack(pady=(0, 20))

        def user_response():
            elapsed = int(time.time() - self.popup_start_time)
            self.add_log(f"✅ Real-time sync: Popup direspon setelah {elapsed} detik")
            self.log_activity("desktop_warning_acknowledged", f'Pop-up ditekan oleh pengguna ({elapsed} detik)') # Log acknowledgment
            self.close_popup(self.popup_window)

        # Button - exact match with web version style
        response_btn = tk.Button(
            content_frame,
            text="Ya, Saya akan kembali",
            command=user_response,
            bg="#28a745",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            padx=20,
            pady=8,
            border=0,
            cursor="hand2",
            relief=tk.FLAT,
            activebackground="#218838", activeforeground="white"
        )
        response_btn.pack(pady=(0, 15))
        
        # Hover effect for button
        def on_enter_btn(e):
            response_btn.config(bg="#218838", pady=10, font=("Segoe UI", 10, "bold"))
        
        def on_leave_btn(e):
            response_btn.config(bg="#28a745", pady=8, font=("Segoe UI", 9, "bold"))
        
        response_btn.bind("<Enter>", on_enter_btn)
        response_btn.bind("<Leave>", on_leave_btn)

        # Play notification sound
        self.play_notification_sound()

        # Set focus and grab
        self.popup_window.focus_force()
        self.popup_window.grab_set() # Grab all input events
        self.popup_window.lift()
        
        # Periodic re-focus to ensure visibility (especially on Windows)
        def keep_on_top():
            if self.popup_active and self.popup_window.winfo_exists():
                self.popup_window.lift()
                self.popup_window.attributes("-topmost", True)
                self.popup_window.after(1000, keep_on_top) # Reschedule every second
        
        keep_on_top()

        # Auto-close timer (synchronized with web app: 60 seconds)
        self.popup_window.after(60000, lambda: self.auto_close_popup(self.popup_window))
        # Handle closing via X button
        self.popup_window.protocol("WM_DELETE_WINDOW", user_response)

        self.add_log(f"🚨 Real-time sync: Popup peringatan #{self.warning_count} ditampilkan")
        self.log_activity("desktop_warning_shown", '[INFO] Pop-up peringatan ditampilkan (Desktop)') # Log warning shown

    def play_notification_sound(self):
        """Play notification sound cross-platform"""
        try:
            if platform.system() == "Windows" and WINDOWS_AVAILABLE:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION) # Standard Windows exclamation sound
            elif platform.system() == "Darwin":  # macOS
                os.system("afplay /System/Library/Sounds/Basso.aiff") # Example macOS sound
            elif platform.system() == "Linux":
                # Try paplay (PulseAudio) or beep (if installed)
                os.system("paplay /usr/share/sounds/alsa/Front_Left.wav 2>/dev/null || beep 2>/dev/null")
        except Exception as e:
            self.add_log(f"Could not play notification sound: {e}")

    def auto_close_popup(self, popup):
        """Auto close popup after timeout"""
        if self.popup_active and popup and popup.winfo_exists():
            self.add_log("⏰ Real-time sync: Popup timeout (60 detik)")
            self.log_activity("desktop_warning_timeout", 'Pop-up timeout (Desktop - tidak direspon)') # Log timeout
            self.close_popup(popup)

    def close_popup(self, popup):
        """Close popup and reset state"""
        if popup and popup.winfo_exists():
            try:
                popup.grab_release() # Release input grab
                popup.destroy() # Close the window
            except Exception as e:
                self.add_log(f"Error closing popup: {e}")
        
        self.popup_active = False
        self.popup_dismissed = True # Mark as dismissed for the current "out of meet" period
        self.add_log("Real-time sync: Popup ditutup")

    def log_activity(self, event_type, message):
        """Log activity to server with enhanced sync"""
        if not self.current_class_id or not self.user_token or not self.session_id or not self.user_id:
            self.add_log(f"Tidak dapat mengirim log '{event_type}': Parameter tidak lengkap")
            return
        
        try:
            response = requests.post(
                f"{self.api_base}/monitoring/log",
                json={
                    "student_id": self.user_id, # Kirim student_id secara eksplisit
                    "class_id": self.current_class_id, 
                    "event_type": event_type, # event_type already prefixed in monitor_loop
                    "message": message,  # Send consistent message
                    "source": "desktop",  # Identify source
                    "session_id": self.session_id,
                    "sync_id": f"desktop_{int(time.time())}_{event_type}",  # Sync ID
                    "original_timestamp": datetime.datetime.now().isoformat()  # Original timestamp
                },
                headers={"Authorization": f"Bearer {self.user_token}"},
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                self.add_log(f"[SYNC SUCCESS] Log '{event_type}' terkirim, status={data.get('status_updated', 'unknown')}")
            else:
                self.add_log(f"[SYNC ERROR] Gagal kirim log (HTTP {response.status_code}) - {response.text}")
        except requests.exceptions.RequestException as e:
            self.add_log(f"[SYNC ERROR] Gagal kirim log (koneksi): {e}")

    def add_log(self, message):
        """Add log message with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        # Use root.after to ensure GUI updates are on the main thread
        self.root.after(0, lambda: self._update_log_text(log_entry))

    def _update_log_text(self, log_entry):
        """Update log text widget"""
        self.log_text.insert(tk.END, log_entry)
        self.log_text.see(tk.END)
        
        # Keep log size manageable (e.g., max 100 lines)
        if int(self.log_text.index('end-1c').split('.')[0]) > 100:
            # Delete the first 20 lines if over 100 lines
            self.log_text.delete(1.0, 20.0)

    def set_monitoring_params(self, class_id, user_token, class_name="", user_id=None):
        """Set monitoring parameters for real-time sync"""
        self.current_class_id = class_id
        self.user_token = user_token
        self.user_id = user_id # Set user_id
        self.class_name = class_name
        if class_name:
            self.class_label.config(text=f"Kelas: {self.class_name}")
        self.add_log(f"🔧 Real-time sync: Parameter diatur - Kelas ID {class_id}, User ID {user_id}, Nama Kelas: {class_name}")

    def run(self):
        """Run the application"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

    def on_closing(self):
        """Handle application closing"""
        if self.monitoring_active:
            if messagebox.askokcancel("Keluar", "Real-time monitoring sedang aktif. Yakin ingin keluar?"):
                self.stop_monitoring()
                self.root.destroy()
        else:
            self.root.destroy()

if __name__ == "__main__":
    # Read arguments from command line
    # Format: python monitoring.py <class_id> <user_id> <user_token> <class_name>
    class_id = None
    user_id = None
    user_token = None
    class_name = None

    if len(sys.argv) > 1:
        try:
            class_id = int(sys.argv[1])
            user_id = int(sys.argv[2])
            user_token = sys.argv[3]
            if len(sys.argv) > 4:
                class_name = sys.argv[4]
        except (ValueError, IndexError) as e:
            print(f"Error parsing command line arguments: {e}")
            print("Usage: python monitoring.py <class_id> <user_id> <user_token> [class_name]")
            # Fallback to manual input if arguments are invalid

    app = MonitoringApp(class_id=class_id, user_id=user_id, user_token=user_token, class_name=class_name)
    
    print("🚀 Real-time Desktop Monitoring App Started")
    print("🔗 Sistem ini akan tersinkronisasi secara real-time dengan web app")
    print("📡 Heartbeat system aktif untuk sinkronisasi status")
    
    app.run()