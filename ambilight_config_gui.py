import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import math
import socket
import numpy as np
import mss
import time
import cv2
from PIL import ImageGrab
from PIL import Image, ImageTk, ImageEnhance
import platform
import threading

class AmbilightConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Ambilight LED Strip Configurator")
        self.root.geometry("1000x700")
        
        # Configuration variables
        self.wled_ip = tk.StringVar(value="192.168.29.4")
        self.wled_port = tk.IntVar(value=21324)
        self.num_leds = tk.IntVar(value=240)
        self.led_start_offset = tk.IntVar(value=106)
        self.traversal_direction = tk.StringVar(value="clockwise")
        
        # User preferences
        self.show_configure_dialog = True  # Don't show again preference
        
        # LED strip configuration
        self.starting_position = None
        self.led_segments = []
        self.is_configuring = False
        self.ambilight_running = False
        self.ambilight_thread = None
        
        # Effect settings
        self.gamma_level = tk.IntVar(value=5)
        self.boost_level = tk.IntVar(value=2)
        self.smoothing_level = tk.IntVar(value=6)
        self.edge_avg_percent = tk.DoubleVar(value=0.1)
        
        # Runtime variables
        self.monitor_region = None
        self.prev_led_colors = None
        
        # GUI state - larger canvas, smaller rectangle
        self.canvas_width = 600
        self.canvas_height = 400
        self.rect_margin = 100
        self.rect_x1 = self.rect_margin
        self.rect_y1 = self.rect_margin
        self.rect_x2 = self.canvas_width - self.rect_margin
        self.rect_y2 = self.canvas_height - self.rect_margin
        
        self.pointer_radius = 10
        self.current_pointer_pos = None
        self.edge_inputs = {}
        self.highlighted_segment = None
        
        self.setup_gui()
        
    def setup_gui(self):
        # Create menu bar
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Generate Configuration", command=self.generate_configuration)
        file_menu.add_separator()
        file_menu.add_command(label="Save Configuration", command=self.save_configuration)
        file_menu.add_command(label="Load Configuration", command=self.load_configuration)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Title
        title_label = ttk.Label(main_frame, text="Ambilight LED Strip Configurator", 
                               font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 20))
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Configuration tab
        config_tab = ttk.Frame(notebook)
        notebook.add(config_tab, text="Configuration")
        
        # Effects tab
        effects_tab = ttk.Frame(notebook)
        notebook.add(effects_tab, text="Effects & Settings")
        
        self.setup_config_tab(config_tab)
        self.setup_effects_tab(effects_tab)
        
    def setup_config_tab(self, parent):
        # Create scrollable frame
        canvas = tk.Canvas(parent)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Top frame for basic settings
        settings_frame = ttk.LabelFrame(scrollable_frame, text="Basic Settings")
        settings_frame.pack(fill=tk.X, pady=(0, 20), padx=10)
        
        # Settings grid
        ttk.Label(settings_frame, text="WLED IP:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.wled_ip, width=15).grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="WLED Port:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.wled_port, width=10).grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Total LEDs:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.num_leds, width=10).grid(row=1, column=1, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Skip first LEDs:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.led_start_offset, width=10).grid(row=1, column=3, padx=5, pady=5)
        
        # Add traversal direction selector
        ttk.Label(settings_frame, text="Traversal Direction:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        direction_combo = ttk.Combobox(settings_frame, textvariable=self.traversal_direction, 
                                     values=["clockwise", "counter-clockwise"], state="readonly", width=12)
        direction_combo.grid(row=2, column=1, padx=5, pady=5)
        
        # Configuration frame
        config_frame = ttk.LabelFrame(scrollable_frame, text="LED Strip Configuration")
        config_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20), padx=10)
        
        # Instructions
        instructions = """Instructions:
1. Click anywhere on the rectangle edge to set your LED strip starting position
2. Choose traversal direction (clockwise/counter-clockwise)
3. Enter the number of LEDs for each edge segment
4. Configure individual segment directions if needed
5. Configure effects in the Effects tab
6. Click 'Start Ambilight' to begin"""
        
        ttk.Label(config_frame, text=instructions, justify=tk.LEFT).pack(anchor=tk.W, padx=10, pady=5)
        
        # Canvas for interactive configuration
        self.canvas = tk.Canvas(config_frame, width=self.canvas_width, height=self.canvas_height, 
                               bg='white', highlightthickness=1, highlightcolor='gray')
        self.canvas.pack(pady=10)
        
        self.draw_rectangle()
        # Remove click handler - we'll use a button instead
        # self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        
        # Add Configure button
        configure_button_frame = ttk.Frame(config_frame)
        configure_button_frame.pack(pady=10)
        
        self.configure_button = ttk.Button(configure_button_frame, text="Configure LED Segments", 
                                         command=self.configure_led_segments)
        self.configure_button.pack()
        
        # Primary action button frame
        action_frame = ttk.Frame(config_frame)
        action_frame.pack(pady=20)
        
        # Create the main Start/Stop button - larger and more prominent
        self.start_stop_button = tk.Button(action_frame, text="🚀 Start Ambilight", 
                                         command=self.toggle_ambilight,
                                         font=("Arial", 14, "bold"),
                                         bg="#4CAF50", fg="white", 
                                         activebackground="#45a049", activeforeground="white",
                                         padx=30, pady=15, relief="raised", bd=3)
        self.start_stop_button.pack()
        
        # Configuration display
        self.config_text = tk.Text(config_frame, height=6, width=100)
        self.config_text.pack(fill=tk.X, padx=10, pady=5)
        
        # Pack scrollable components
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel - fix: bind to specific canvas and add error handling
        def _on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except tk.TclError:
                pass  # Canvas was destroyed
        canvas.bind("<MouseWheel>", _on_mousewheel)
        canvas.focus_set()
        canvas.bind("<Enter>", lambda e: canvas.focus_set())
        
    def setup_effects_tab(self, parent):
        # Effects settings
        effects_frame = ttk.LabelFrame(parent, text="Color & Effect Settings")
        effects_frame.pack(fill=tk.X, pady=10, padx=10)
        
        # Gamma correction
        ttk.Label(effects_frame, text="Gamma Level (0-10):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        gamma_scale = ttk.Scale(effects_frame, from_=0, to=10, variable=self.gamma_level, orient=tk.HORIZONTAL, length=200)
        gamma_scale.grid(row=0, column=1, padx=5, pady=5)
        ttk.Label(effects_frame, textvariable=self.gamma_level).grid(row=0, column=2, padx=5)
        
        # Color boost
        ttk.Label(effects_frame, text="Color Boost (0-10):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        boost_scale = ttk.Scale(effects_frame, from_=0, to=10, variable=self.boost_level, orient=tk.HORIZONTAL, length=200)
        boost_scale.grid(row=1, column=1, padx=5, pady=5)
        ttk.Label(effects_frame, textvariable=self.boost_level).grid(row=1, column=2, padx=5)
        
        # Smoothing
        ttk.Label(effects_frame, text="Smoothing (0-10):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        smooth_scale = ttk.Scale(effects_frame, from_=0, to=10, variable=self.smoothing_level, orient=tk.HORIZONTAL, length=200)
        smooth_scale.grid(row=2, column=1, padx=5, pady=5)
        ttk.Label(effects_frame, textvariable=self.smoothing_level).grid(row=2, column=2, padx=5)
        
        # Edge sampling percentage
        ttk.Label(effects_frame, text="Edge Sample % (0.05-0.5):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        edge_scale = ttk.Scale(effects_frame, from_=0.05, to=0.5, variable=self.edge_avg_percent, orient=tk.HORIZONTAL, length=200)
        edge_scale.grid(row=3, column=1, padx=5, pady=5)
        edge_label = ttk.Label(effects_frame, text="")
        edge_label.grid(row=3, column=2, padx=5)
        
        def update_edge_label(*args):
            edge_label.config(text=f"{self.edge_avg_percent.get():.2f}")
        self.edge_avg_percent.trace('w', update_edge_label)
        update_edge_label()
        
        # Status frame
        status_frame = ttk.LabelFrame(parent, text="Status")
        status_frame.pack(fill=tk.X, pady=10, padx=10)
        
        self.status_label = ttk.Label(status_frame, text="Status: Ready", font=("Arial", 10))
        self.status_label.pack(pady=10)

    def draw_rectangle(self):
        self.canvas.delete("all")
        
        # Draw main rectangle
        self.canvas.create_rectangle(self.rect_x1, self.rect_y1, self.rect_x2, self.rect_y2, 
                                   outline='black', width=3, fill='lightgray')
        
        # Draw edge labels
        mid_x = (self.rect_x1 + self.rect_x2) // 2
        mid_y = (self.rect_y1 + self.rect_y2) // 2
        
        self.canvas.create_text(mid_x, self.rect_y1 - 20, text="TOP", font=("Arial", 12, "bold"))
        self.canvas.create_text(mid_x, self.rect_y2 + 20, text="BOTTOM", font=("Arial", 12, "bold"))
        self.canvas.create_text(self.rect_x1 - 30, mid_y, text="LEFT", font=("Arial", 12, "bold"), angle=90)
        self.canvas.create_text(self.rect_x2 + 30, mid_y, text="RIGHT", font=("Arial", 12, "bold"), angle=90)
        
        # Highlight segment if hovering
        if self.highlighted_segment:
            self.highlight_segment_on_canvas(self.highlighted_segment)
        
        # Draw current pointer if exists
        if self.current_pointer_pos:
            x, y = self.current_pointer_pos
            self.canvas.create_oval(x - self.pointer_radius, y - self.pointer_radius,
                                  x + self.pointer_radius, y + self.pointer_radius,
                                  fill='red', outline='darkred', width=3)
            
            # Show starting position text
            pos_text = self.get_position_description(x, y)
            self.canvas.create_text(x, y - 30, text=f"START: {pos_text}", 
                                  font=("Arial", 10, "bold"), fill='red')
    
    def highlight_segment_on_canvas(self, segment_name):
        """Highlight a specific segment on the canvas"""
        if not segment_name:
            return
            
        # Define segment coordinates based on segment name
        highlight_coords = self.get_segment_coordinates(segment_name)
        if highlight_coords:
            self.canvas.create_line(*highlight_coords, fill='orange', width=8, tags="highlight")
    
    def get_segment_coordinates(self, segment_name):
        """Get canvas coordinates for highlighting a segment"""
        mid_x = (self.rect_x1 + self.rect_x2) // 2
        mid_y = (self.rect_y1 + self.rect_y2) // 2
        
        coords_map = {
            # Full edges
            "top": (self.rect_x1, self.rect_y1, self.rect_x2, self.rect_y1),
            "bottom": (self.rect_x1, self.rect_y2, self.rect_x2, self.rect_y2),
            "left": (self.rect_x1, self.rect_y1, self.rect_x1, self.rect_y2),
            "right": (self.rect_x2, self.rect_y1, self.rect_x2, self.rect_y2),
            
            # Half edges
            "top_left": (self.rect_x1, self.rect_y1, mid_x, self.rect_y1),
            "top_right": (mid_x, self.rect_y1, self.rect_x2, self.rect_y1),
            "bottom_left": (self.rect_x1, self.rect_y2, mid_x, self.rect_y2),
            "bottom_right": (mid_x, self.rect_y2, self.rect_x2, self.rect_y2),
            "left_top": (self.rect_x1, self.rect_y1, self.rect_x1, mid_y),
            "left_bottom": (self.rect_x1, mid_y, self.rect_x1, self.rect_y2),
            "right_top": (self.rect_x2, self.rect_y1, self.rect_x2, mid_y),
            "right_bottom": (self.rect_x2, mid_y, self.rect_x2, self.rect_y2),
        }
        
        return coords_map.get(segment_name)
    
    def on_canvas_motion(self, event):
        # Show preview of where click would place pointer
        x, y = event.x, event.y
        edge_pos = self.get_edge_position(x, y)
        
        if edge_pos:
            self.canvas.config(cursor="hand2")
            # Show tooltip-like text for where the starting position would be
            pos_desc = self.get_position_description(*edge_pos)
            # Clear previous tooltip and create new one
            self.canvas.delete("tooltip")
            self.canvas.create_text(edge_pos[0], edge_pos[1] - 40, text=f"Click 'Configure' to set start: {pos_desc}", 
                                  font=("Arial", 8), fill='blue', tags="tooltip")
        else:
            self.canvas.config(cursor="")
            self.canvas.delete("tooltip")
    
    def configure_led_segments(self):
        """Configure LED segments - either initial setup or reconfiguration"""
        # Check if we already have a starting position set
        if self.current_pointer_pos and hasattr(self, 'led_segments') and self.led_segments:
            # Already configured - just show edge inputs for modification
            self.show_edge_inputs()
        else:
            # Need to set or change starting position
            if self.show_configure_dialog:
                # Create custom dialog with "Don't show again" option
                dialog = tk.Toplevel(self.root)
                dialog.title("Set Starting Position")
                dialog.geometry("400x200")
                dialog.transient(self.root)
                dialog.grab_set()
                
                # Center the dialog
                dialog.update_idletasks()
                x = (dialog.winfo_screenwidth() // 2) - (dialog.winfo_width() // 2)
                y = (dialog.winfo_screenheight() // 2) - (dialog.winfo_height() // 2)
                dialog.geometry(f"400x200+{x}+{y}")
                
                # Message
                message_frame = ttk.Frame(dialog)
                message_frame.pack(expand=True, fill=tk.BOTH, padx=20, pady=20)
                
                ttk.Label(message_frame, text="Set Starting Position", 
                         font=("Arial", 12, "bold")).pack(pady=(0, 10))
                
                ttk.Label(message_frame, text="Click on any edge of the rectangle to set your LED strip starting position.\n\nYou can click different edges to change the starting position.",
                         wraplength=350, justify=tk.CENTER).pack(pady=(0, 15))
                
                # Don't show again checkbox
                dont_show_var = tk.BooleanVar()
                ttk.Checkbutton(message_frame, text="Don't show this dialog again", 
                               variable=dont_show_var).pack(pady=(0, 15))
                
                # Buttons
                button_frame = ttk.Frame(message_frame)
                button_frame.pack()
                
                def on_ok():
                    if dont_show_var.get():
                        self.show_configure_dialog = False
                    dialog.destroy()
                    self.enable_position_selection()
                
                def on_cancel():
                    dialog.destroy()
                
                ttk.Button(button_frame, text="OK", command=on_ok).pack(side=tk.LEFT, padx=5)
                ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT, padx=5)
                
                dialog.wait_window()
            else:
                # Just enable position selection directly
                self.enable_position_selection()
    
    def enable_position_selection(self):
        """Enable clicking on edges to select starting position"""
        # Enable click handler for selecting starting position
        def on_canvas_click_temp(event):
            x, y = event.x, event.y
            edge_pos = self.get_edge_position(x, y)
            if edge_pos:
                self.current_pointer_pos = edge_pos
                self.starting_position = self.get_position_description(*edge_pos)
                self.draw_rectangle()
                # Update button text
                self.configure_button.config(text="Reconfigure LED Segments")
                # Remove click handler and show segments window
                self.canvas.unbind("<Button-1>")
                self.show_edge_inputs()
        
        # Bind click handler for selecting starting position
        self.canvas.bind("<Button-1>", on_canvas_click_temp)
    
    def get_edge_position(self, x, y, tolerance=20):
        """Return the closest point on rectangle edge if within tolerance"""
        
        # Check top edge
        if abs(y - self.rect_y1) < tolerance and self.rect_x1 <= x <= self.rect_x2:
            return (x, self.rect_y1)
        
        # Check bottom edge
        if abs(y - self.rect_y2) < tolerance and self.rect_x1 <= x <= self.rect_x2:
            return (x, self.rect_y2)
        
        # Check left edge
        if abs(x - self.rect_x1) < tolerance and self.rect_y1 <= y <= self.rect_y2:
            return (self.rect_x1, y)
        
        # Check right edge
        if abs(x - self.rect_x2) < tolerance and self.rect_y1 <= y <= self.rect_y2:
            return (self.rect_x2, y)
        
        return None
    
    def get_position_description(self, x, y):
        """Get description of position on rectangle"""
        mid_x = (self.rect_x1 + self.rect_x2) // 2
        mid_y = (self.rect_y1 + self.rect_y2) // 2
        tolerance = 25  # Pixels tolerance for "middle" detection
        
        if y == self.rect_y1:  # Top edge
            if abs(x - self.rect_x1) < tolerance:
                return "top_left_corner"
            elif abs(x - self.rect_x2) < tolerance:
                return "top_right_corner"
            elif abs(x - mid_x) < tolerance:
                return "top_middle"
            elif x < mid_x:
                return "top_left_side"
            else:
                return "top_right_side"
        elif y == self.rect_y2:  # Bottom edge
            if abs(x - self.rect_x1) < tolerance:
                return "bottom_left_corner"
            elif abs(x - self.rect_x2) < tolerance:
                return "bottom_right_corner"
            elif abs(x - mid_x) < tolerance:
                return "bottom_middle"
            elif x < mid_x:
                return "bottom_left_side"
            else:
                return "bottom_right_side"
        elif x == self.rect_x1:  # Left edge
            if abs(y - self.rect_y1) < tolerance:
                return "left_top_corner"
            elif abs(y - self.rect_y2) < tolerance:
                return "left_bottom_corner"
            elif abs(y - mid_y) < tolerance:
                return "left_middle"
            elif y < mid_y:
                return "left_top_side"
            else:
                return "left_bottom_side"
        elif x == self.rect_x2:  # Right edge
            if abs(y - self.rect_y1) < tolerance:
                return "right_top_corner"
            elif abs(y - self.rect_y2) < tolerance:
                return "right_bottom_corner"
            elif abs(y - mid_y) < tolerance:
                return "right_middle"
            elif y < mid_y:
                return "right_top_side"
            else:
                return "right_bottom_side"
        
        return "unknown"
    
    def show_edge_inputs(self):
        """Show input fields for LED counts on each edge"""
        if not self.starting_position:
            return
        
        # Clear previous inputs
        for widget in self.edge_inputs.values():
            widget.destroy()
        self.edge_inputs.clear()
        
        # Create input window
        input_window = tk.Toplevel(self.root)
        input_window.title("Configure LED Segments")
        input_window.geometry("600x700")
        input_window.transient(self.root)
        input_window.grab_set()
        
        # Create scrollable frame
        canvas = tk.Canvas(input_window)
        scrollbar = ttk.Scrollbar(input_window, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Instructions
        ttk.Label(scrollable_frame, text=f"Starting from: {self.starting_position}", 
                 font=("Arial", 12, "bold")).pack(pady=10)
        
        ttk.Label(scrollable_frame, text=f"Traversal direction: {self.traversal_direction.get()}", 
                 font=("Arial", 10)).pack(pady=2)
        
        ttk.Label(scrollable_frame, text="Enter the number of LEDs and direction for each segment:", 
                 font=("Arial", 10)).pack(pady=5)
        
        # Generate edge sequence based on starting position
        edge_sequence = self.generate_edge_sequence()
        
        # Create existing configuration lookup for pre-populating values
        existing_config = {}
        if hasattr(self, 'led_segments') and self.led_segments:
            for edge_name, count, description, direction in self.led_segments:
                existing_config[edge_name] = {'count': count, 'direction': direction}
        
        # Create input fields for each edge
        self.segment_vars = {}
        self.direction_vars = {}
        input_frame = ttk.Frame(scrollable_frame)
        input_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        
        for i, (edge_name, description) in enumerate(edge_sequence):
            row_frame = ttk.Frame(input_frame)
            row_frame.pack(fill=tk.X, pady=8)
            
            # Segment number and description
            label = ttk.Label(row_frame, text=f"{i+1}. {description}:", width=35, anchor=tk.W)
            label.pack(side=tk.LEFT)
            
            # LED count entry - use existing value if available
            default_count = existing_config.get(edge_name, {}).get('count', 20)
            count_var = tk.IntVar(value=default_count)
            self.segment_vars[edge_name] = count_var
            ttk.Label(row_frame, text="LEDs:").pack(side=tk.LEFT, padx=(10, 2))
            entry = ttk.Entry(row_frame, textvariable=count_var, width=8)
            entry.pack(side=tk.LEFT, padx=(0, 10))
            
            # Direction selection - use existing value if available
            default_direction = existing_config.get(edge_name, {}).get('direction', 'normal')
            direction_var = tk.StringVar(value=default_direction)
            self.direction_vars[edge_name] = direction_var
            ttk.Label(row_frame, text="Direction:").pack(side=tk.LEFT, padx=(10, 2))
            direction_combo = ttk.Combobox(row_frame, textvariable=direction_var, 
                                         values=["normal", "reversed"], state="readonly", width=10)
            direction_combo.pack(side=tk.LEFT)
            
            # Add hover events for highlighting
            def on_enter(event, segment=edge_name):
                self.highlighted_segment = segment
                self.draw_rectangle()
            
            def on_leave(event):
                self.highlighted_segment = None
                self.draw_rectangle()
            
            label.bind("<Enter>", on_enter)
            label.bind("<Leave>", on_leave)
            entry.bind("<Enter>", on_enter)
            entry.bind("<Leave>", on_leave)
            direction_combo.bind("<Enter>", on_enter)
            direction_combo.bind("<Leave>", on_leave)
        
        # Show status if pre-populated
        if existing_config:
            status_label = ttk.Label(scrollable_frame, text="✓ Configuration loaded from saved file", 
                                   foreground="green", font=("Arial", 9, "italic"))
            status_label.pack(pady=(5, 10))
        
        # Buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.pack(fill=tk.X, padx=20, pady=20)
        
        def apply_config():
            self.led_segments = []
            for edge_name, description in edge_sequence:
                count = self.segment_vars[edge_name].get()
                direction = self.direction_vars[edge_name].get()
                self.led_segments.append((edge_name, count, description, direction))
            input_window.destroy()
            self.highlighted_segment = None
            self.update_config_display()
        
        ttk.Button(button_frame, text="Apply Configuration", command=apply_config).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=input_window.destroy).pack(side=tk.RIGHT)
        
        # Pack scrollable components
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Bind mousewheel - fix: bind to specific canvas and add error handling
        def _on_mousewheel(event):
            try:
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")
            except tk.TclError:
                pass  # Canvas was destroyed
        canvas.bind("<MouseWheel>", _on_mousewheel)
        canvas.focus_set()
        canvas.bind("<Enter>", lambda e: canvas.focus_set())
        
        # Cleanup when window is destroyed
        def on_destroy():
            try:
                canvas.unbind("<MouseWheel>")
            except tk.TclError:
                pass
        input_window.protocol("WM_DELETE_WINDOW", lambda: (on_destroy(), input_window.destroy()))
    
    def generate_edge_sequence(self):
        """Generate the sequence of edges based on starting position and traversal direction"""
        if not self.starting_position:
            return []
        
        is_clockwise = self.traversal_direction.get() == "clockwise"
        
        # Define edge sequences based on starting position
        if "corner" in self.starting_position:
            return self.generate_corner_sequence(is_clockwise)
        else:
            return self.generate_middle_sequence(is_clockwise)
    
    def generate_corner_sequence(self, is_clockwise):
        """Generate sequence for corner starting positions"""
        sequences = {
            "top_left_corner": {
                True: [  # clockwise
                    ("top", "Top edge (left to right)"),
                    ("right", "Right edge (top to bottom)"),
                    ("bottom", "Bottom edge (right to left)"),
                    ("left", "Left edge (bottom to top)")
                ],
                False: [  # counter-clockwise
                    ("left", "Left edge (top to bottom)"),
                    ("bottom", "Bottom edge (left to right)"),
                    ("right", "Right edge (bottom to top)"),
                    ("top", "Top edge (right to left)")
                ]
            },
            "top_right_corner": {
                True: [  # clockwise
                    ("right", "Right edge (top to bottom)"),
                    ("bottom", "Bottom edge (right to left)"),
                    ("left", "Left edge (bottom to top)"),
                    ("top", "Top edge (left to right)")
                ],
                False: [  # counter-clockwise
                    ("top", "Top edge (right to left)"),
                    ("left", "Left edge (top to bottom)"),
                    ("bottom", "Bottom edge (left to right)"),
                    ("right", "Right edge (bottom to top)")
                ]
            },
            "bottom_right_corner": {
                True: [  # clockwise
                    ("bottom", "Bottom edge (right to left)"),
                    ("left", "Left edge (bottom to top)"),
                    ("top", "Top edge (left to right)"),
                    ("right", "Right edge (top to bottom)")
                ],
                False: [  # counter-clockwise
                    ("right", "Right edge (bottom to top)"),
                    ("top", "Top edge (right to left)"),
                    ("left", "Left edge (top to bottom)"),
                    ("bottom", "Bottom edge (left to right)")
                ]
            },
            "bottom_left_corner": {
                True: [  # clockwise
                    ("left", "Left edge (bottom to top)"),
                    ("top", "Top edge (left to right)"),
                    ("right", "Right edge (top to bottom)"),
                    ("bottom", "Bottom edge (right to left)")
                ],
                False: [  # counter-clockwise
                    ("bottom", "Bottom edge (left to right)"),
                    ("right", "Right edge (bottom to top)"),
                    ("top", "Top edge (right to left)"),
                    ("left", "Left edge (top to bottom)")
                ]
            }
        }
        
        return sequences.get(self.starting_position, {}).get(is_clockwise, [])
    
    def generate_middle_sequence(self, is_clockwise):
        """Generate sequence for middle/side starting positions"""
        sequences = {
            "right_middle": {
                True: [  # clockwise from right middle
                    ("right_bottom", "Right edge (middle to bottom)"),
                    ("bottom", "Bottom edge (right to left)"),
                    ("left", "Left edge (bottom to top)"),
                    ("top", "Top edge (left to right)"),
                    ("right_top", "Right edge (top to middle)")
                ],
                False: [  # counter-clockwise from right middle
                    ("right_top", "Right edge (middle to top)"),
                    ("top", "Top edge (right to left)"),
                    ("left", "Left edge (top to bottom)"),
                    ("bottom", "Bottom edge (left to right)"),
                    ("right_bottom", "Right edge (bottom to middle)")
                ]
            },
            "bottom_middle": {
                True: [  # clockwise from bottom middle
                    ("bottom_left", "Bottom edge (middle to left)"),
                    ("left", "Left edge (bottom to top)"),
                    ("top", "Top edge (left to right)"),
                    ("right", "Right edge (top to bottom)"),
                    ("bottom_right", "Bottom edge (right to middle)")
                ],
                False: [  # counter-clockwise from bottom middle
                    ("bottom_right", "Bottom edge (middle to right)"),
                    ("right", "Right edge (bottom to top)"),
                    ("top", "Top edge (right to left)"),
                    ("left", "Left edge (top to bottom)"),
                    ("bottom_left", "Bottom edge (left to middle)")
                ]
            },
            "left_middle": {
                True: [  # clockwise from left middle
                    ("left_top", "Left edge (middle to top)"),
                    ("top", "Top edge (left to right)"),
                    ("right", "Right edge (top to bottom)"),
                    ("bottom", "Bottom edge (right to left)"),
                    ("left_bottom", "Left edge (bottom to middle)")
                ],
                False: [  # counter-clockwise from left middle
                    ("left_bottom", "Left edge (middle to bottom)"),
                    ("bottom", "Bottom edge (left to right)"),
                    ("right", "Right edge (bottom to top)"),
                    ("top", "Top edge (right to left)"),
                    ("left_top", "Left edge (top to middle)")
                ]
            },
            "top_middle": {
                True: [  # clockwise from top middle
                    ("top_right", "Top edge (middle to right)"),
                    ("right", "Right edge (top to bottom)"),
                    ("bottom", "Bottom edge (right to left)"),
                    ("left", "Left edge (bottom to top)"),
                    ("top_left", "Top edge (left to middle)")
                ],
                False: [  # counter-clockwise from top middle
                    ("top_left", "Top edge (middle to left)"),
                    ("left", "Left edge (top to bottom)"),
                    ("bottom", "Bottom edge (left to right)"),
                    ("right", "Right edge (bottom to top)"),
                    ("top_right", "Top edge (right to middle)")
                ]
            }
        }
        
        # Handle side positions (not exactly middle)
        if self.starting_position not in sequences:
            # Map side positions to middle positions for sequence generation
            position_map = {
                "right_top_side": "right_middle",
                "right_bottom_side": "right_middle", 
                "bottom_left_side": "bottom_middle",
                "bottom_right_side": "bottom_middle",
                "left_top_side": "left_middle",
                "left_bottom_side": "left_middle",
                "top_left_side": "top_middle",
                "top_right_side": "top_middle"
            }
            mapped_position = position_map.get(self.starting_position)
            if mapped_position:
                return sequences.get(mapped_position, {}).get(is_clockwise, [])
        
        return sequences.get(self.starting_position, {}).get(is_clockwise, [])
    
    def update_config_display(self):
        """Update the configuration display text"""
        self.config_text.delete(1.0, tk.END)
        
        if not self.led_segments:
            self.config_text.insert(tk.END, "No configuration set. Click on rectangle edge to start.")
            return
        
        config_text = f"LED Strip Configuration:\n"
        config_text += f"Starting Position: {self.starting_position}\n"
        config_text += f"Traversal Direction: {self.traversal_direction.get()}\n"
        config_text += f"Total LEDs: {self.num_leds.get()}\n"
        config_text += f"Skip first: {self.led_start_offset.get()} LEDs\n\n"
        
        config_text += "LED Segments:\n"
        current_led = self.led_start_offset.get()
        total_used = 0
        
        for i, (edge_name, count, description, direction) in enumerate(self.led_segments):
            config_text += f"{i+1}. {description}: LEDs {current_led}-{current_led + count - 1} ({count} LEDs, {direction})\n"
            current_led += count
            total_used += count
        
        config_text += f"\nTotal active LEDs: {total_used}\n"
        config_text += f"Remaining LEDs: {self.num_leds.get() - self.led_start_offset.get() - total_used}"
        
        self.config_text.insert(tk.END, config_text)
    
    def generate_configuration(self):
        """Generate the final configuration code"""
        if not self.led_segments:
            messagebox.showerror("Error", "Please configure LED segments first.")
            return
        
        # Show generated configuration
        config_window = tk.Toplevel(self.root)
        config_window.title("Generated Configuration")
        config_window.geometry("600x400")
        
        config_code = self.generate_config_code()
        
        text_widget = tk.Text(config_window, wrap=tk.WORD)
        scrollbar = ttk.Scrollbar(config_window, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        text_widget.insert(tk.END, config_code)
    
    def generate_config_code(self):
        """Generate Python configuration code"""
        code = f"""# Generated LED Strip Configuration
WLED_IP = "{self.wled_ip.get()}"
WLED_UDP_PORT = {self.wled_port.get()}
NUM_LEDS = {self.num_leds.get()}
LED_START_OFFSET = {self.led_start_offset.get()}

# Starting position: {self.starting_position}
# Traversal direction: {self.traversal_direction.get()}
LED_STRIP_FLOW = [
"""
        
        for edge_name, count, description, direction in self.led_segments:
            code += f'    ("{edge_name}", {count}, "{direction}"),  # {description}\n'
        
        code += "]\n"
        return code
    
    def save_configuration(self):
        """Save configuration to JSON file"""
        if not self.led_segments:
            messagebox.showerror("Error", "No configuration to save.")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            config = {
                "wled_ip": self.wled_ip.get(),
                "wled_port": self.wled_port.get(),
                "num_leds": self.num_leds.get(),
                "led_start_offset": self.led_start_offset.get(),
                "traversal_direction": self.traversal_direction.get(),
                "starting_position": self.starting_position,
                "led_segments": self.led_segments,
                "gamma_level": self.gamma_level.get(),
                "boost_level": self.boost_level.get(),
                "smoothing_level": self.smoothing_level.get(),
                "edge_avg_percent": self.edge_avg_percent.get()
            }
            
            with open(filename, 'w') as f:
                json.dump(config, f, indent=2)
            
            messagebox.showinfo("Success", f"Configuration saved to {filename}")
    
    def load_configuration(self):
        """Load configuration from JSON file"""
        filename = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        
        if filename:
            try:
                with open(filename, 'r') as f:
                    config = json.load(f)
                
                # Load basic settings
                self.wled_ip.set(config["wled_ip"])
                self.wled_port.set(config["wled_port"])
                self.num_leds.set(config["num_leds"])
                self.led_start_offset.set(config["led_start_offset"])
                self.traversal_direction.set(config.get("traversal_direction", "clockwise"))
                self.starting_position = config["starting_position"]
                self.led_segments = config["led_segments"]
                
                # Load effect settings if available
                self.gamma_level.set(config.get("gamma_level", 5))
                self.boost_level.set(config.get("boost_level", 2))
                self.smoothing_level.set(config.get("smoothing_level", 6))
                self.edge_avg_percent.set(config.get("edge_avg_percent", 0.1))
                
                # Update the configuration display
                self.update_config_display()
                
                # Update the canvas to show the starting position
                if self.starting_position:
                    # Find the position on canvas based on starting_position string
                    self.current_pointer_pos = self.get_canvas_position_from_description(self.starting_position)
                    self.draw_rectangle()
                    # Update button text since we now have a configuration
                    self.configure_button.config(text="Reconfigure LED Segments")
                
                messagebox.showinfo("Success", f"Configuration loaded from {filename}")
                
                # Automatically show the segment configuration window for easy editing
                if self.starting_position and self.led_segments:
                    # Ask user if they want to edit the configuration
                    response = messagebox.askyesno(
                        "Edit Configuration", 
                        "Configuration loaded successfully!\n\nWould you like to open the segment editor to review or modify the LED counts and directions?"
                    )
                    if response:
                        self.show_edge_inputs()
                
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load configuration: {str(e)}")
    
    def get_canvas_position_from_description(self, position_desc):
        """Convert position description back to canvas coordinates"""
        mid_x = (self.rect_x1 + self.rect_x2) // 2
        mid_y = (self.rect_y1 + self.rect_y2) // 2
        
        # Map position descriptions to canvas coordinates
        position_map = {
            # Corners
            "top_left_corner": (self.rect_x1, self.rect_y1),
            "top_right_corner": (self.rect_x2, self.rect_y1),
            "bottom_left_corner": (self.rect_x1, self.rect_y2),
            "bottom_right_corner": (self.rect_x2, self.rect_y2),
            
            # Middle positions
            "top_middle": (mid_x, self.rect_y1),
            "bottom_middle": (mid_x, self.rect_y2),
            "left_middle": (self.rect_x1, mid_y),
            "right_middle": (self.rect_x2, mid_y),
            
            # Side positions (approximations)
            "top_left_side": (self.rect_x1 + (mid_x - self.rect_x1) // 2, self.rect_y1),
            "top_right_side": (mid_x + (self.rect_x2 - mid_x) // 2, self.rect_y1),
            "bottom_left_side": (self.rect_x1 + (mid_x - self.rect_x1) // 2, self.rect_y2),
            "bottom_right_side": (mid_x + (self.rect_x2 - mid_x) // 2, self.rect_y2),
            "left_top_side": (self.rect_x1, self.rect_y1 + (mid_y - self.rect_y1) // 2),
            "left_bottom_side": (self.rect_x1, mid_y + (self.rect_y2 - mid_y) // 2),
            "right_top_side": (self.rect_x2, self.rect_y1 + (mid_y - self.rect_y1) // 2),
            "right_bottom_side": (self.rect_x2, mid_y + (self.rect_y2 - mid_y) // 2),
        }
        
        return position_map.get(position_desc, (mid_x, self.rect_y2))  # Default to bottom middle
    
    def select_monitor_and_region(self):
        """Select monitor and capture region"""
        try:
            with mss.mss() as sct:
                monitors = sct.monitors[1:]  # Skip the "all monitors" entry
                
                if not monitors:
                    messagebox.showerror("Error", "No monitors detected.")
                    return None
                
                if len(monitors) == 1:
                    monitor_idx = 0
                else:
                    # Show monitor selection dialog
                    monitor_window = tk.Toplevel(self.root)
                    monitor_window.title("Select Monitor")
                    monitor_window.geometry("400x300")
                    monitor_window.transient(self.root)
                    monitor_window.grab_set()
                    
                    ttk.Label(monitor_window, text="Select Monitor:", font=("Arial", 12, "bold")).pack(pady=10)
                    
                    monitor_var = tk.IntVar(value=0)
                    for i, mon in enumerate(monitors):
                        text = f"Monitor {i+1}: {mon['width']}x{mon['height']} at ({mon['left']},{mon['top']})"
                        ttk.Radiobutton(monitor_window, text=text, variable=monitor_var, value=i).pack(anchor=tk.W, padx=20, pady=5)
                    
                    selected_monitor = None
                    
                    def confirm_monitor():
                        nonlocal selected_monitor
                        selected_monitor = monitor_var.get()
                        monitor_window.destroy()
                    
                    ttk.Button(monitor_window, text="Select", command=confirm_monitor).pack(pady=20)
                    monitor_window.wait_window()
                    
                    if selected_monitor is None:
                        return None
                    monitor_idx = selected_monitor
                
                # Get selected monitor
                selected_monitor = monitors[monitor_idx]
                
                # Create region selection window
                return self.select_region_on_monitor(selected_monitor)
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to select monitor: {str(e)}")
            return None
    
    def select_region_on_monitor(self, monitor):
        """Select capture region on the specified monitor"""
        # Don't create a new root - use the existing one
        print(f"Creating region selection window for monitor: {monitor}")
        
        top = tk.Toplevel(self.root)
        top.geometry(f"{monitor['width']}x{monitor['height']}+{monitor['left']}+{monitor['top']}")
        top.overrideredirect(True)
        top.lift()
        top.attributes("-topmost", True)
        top.attributes('-alpha', 0.3)  # Semi-transparent window
        top.grab_set()  # Make modal
        
        canvas = tk.Canvas(top, cursor="cross", width=monitor['width'], height=monitor['height'], 
                          highlightthickness=0, bg='black')
        canvas.pack(fill=tk.BOTH, expand=True)
        
        start_x = start_y = rect = None
        region = {}
        selection_made = False
        
        def on_button_press(event):
            nonlocal start_x, start_y, rect
            print(f"Mouse press at: {event.x}, {event.y}")
            start_x, start_y = event.x, event.y
            rect = canvas.create_rectangle(start_x, start_y, start_x, start_y, outline='white', width=2)
        
        def on_mouse_drag(event):
            if rect:
                canvas.coords(rect, start_x, start_y, event.x, event.y)
        
        def on_button_release(event):
            nonlocal selection_made
            print(f"Mouse release at: {event.x}, {event.y}")
            x1 = min(start_x, event.x)
            y1 = min(start_y, event.y)
            x2 = max(start_x, event.x)
            y2 = max(start_y, event.y)
            canvas.delete(rect)
            region['coords'] = (x1 + monitor['left'], y1 + monitor['top'], x2 - x1, y2 - y1)
            print(f"Region selected: {region['coords']}")
            selection_made = True
            top.quit()  # Exit mainloop
        
        def on_escape(event):
            nonlocal selection_made
            print("Escape pressed - canceling selection")
            selection_made = False
            top.quit()
        
        canvas.bind("<Button-1>", on_button_press)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_button_release)
        top.bind("<Escape>", on_escape)
        canvas.focus_set()
        
        # Add instruction text
        canvas.create_text(monitor['width']//2, 50, text="Drag to select capture region (ESC to cancel)", 
                          fill='white', font=("Arial", 16, "bold"))
        
        print("Starting region selection mainloop...")
        top.mainloop()
        
        print("Region selection mainloop ended")
        top.destroy()
        
        if selection_made and 'coords' in region:
            print(f"Returning region: {region['coords']}")
            return region['coords']
        else:
            print("No region selected")
            return None
    
    def start_ambilight(self):
        """Start the ambilight effect"""
        print("START_AMBILIGHT called!")
        
        if not self.led_segments:
            print("ERROR: No LED segments configured!")
            messagebox.showerror("Error", "Please configure LED segments first.")
            return
        
        print(f"LED segments found: {len(self.led_segments)}")
        for i, (edge_name, count, description, direction) in enumerate(self.led_segments):
            print(f"  Segment {i+1}: {edge_name} -> {count} LEDs ({description}, {direction})")
        
        if self.ambilight_running:
            print("Ambilight already running!")
            messagebox.showinfo("Info", "Ambilight is already running.")
            return
        
        try:
            print("Updating status to selecting monitor...")
            self.status_label.config(text="Status: Selecting monitor and region...")
            # Update button to show "Selecting..." state
            self.start_stop_button.config(text="⏳ Selecting Region...", bg="#FF9800", fg="white")
            self.start_stop_button.config(activebackground="#F57C00", activeforeground="white")
            self.start_stop_button.config(relief="flat", bd=2)
            self.root.update()
        except tk.TclError:
            print("Widget was destroyed!")
            return  # Widget was destroyed
        
        print("Calling select_monitor_and_region...")
        # Select monitor and region
        self.monitor_region = self.select_monitor_and_region()
        print(f"Monitor region selected: {self.monitor_region}")
        
        if not self.monitor_region:
            print("No monitor region selected!")
            try:
                self.status_label.config(text="Status: Ready")
            except tk.TclError:
                pass
            return
        
        # CRITICAL FIX: Capture all tkinter variables before starting thread
        print("Capturing configuration values...")
        self.config_snapshot = {
            'wled_ip': self.wled_ip.get(),
            'wled_port': self.wled_port.get(),
            'num_leds': self.num_leds.get(),
            'led_start_offset': self.led_start_offset.get(),
            'traversal_direction': self.traversal_direction.get(),
            'gamma_level': self.gamma_level.get(),
            'boost_level': self.boost_level.get(),
            'smoothing_level': self.smoothing_level.get(),
            'edge_avg_percent': self.edge_avg_percent.get()
        }
        print(f"Config snapshot: {self.config_snapshot}")
        
        print("Setting ambilight_running = True and starting thread...")
        self.ambilight_running = True
        self.prev_led_colors = None
        self.ambilight_thread = threading.Thread(target=self.ambilight_worker, daemon=True)
        self.ambilight_thread.start()
        print("Thread started!")
        
        try:
            self.status_label.config(text="Status: Ambilight running...")
            self.start_stop_button.config(text="⚙️ Stop Ambilight", bg="#F44336", fg="white")
            self.start_stop_button.config(activebackground="#D32F2F", activeforeground="white")
            self.start_stop_button.config(relief="sunken", bd=5)
            self.start_stop_button.update()
        except tk.TclError:
            pass  # Widget was destroyed
    
    def stop_ambilight(self):
        """Stop the ambilight effect"""
        self.ambilight_running = False
        if self.ambilight_thread:
            self.ambilight_thread.join(timeout=1)
        try:
            self.status_label.config(text="Status: Stopped")
            self.start_stop_button.config(text="🚀 Start Ambilight", bg="#4CAF50", fg="white")
            self.start_stop_button.config(activebackground="#45a049", activeforeground="white")
            self.start_stop_button.config(relief="raised", bd=3)
            self.start_stop_button.update()
        except tk.TclError:
            pass  # Widget was destroyed
    
    def enhance_color(self, rgb):
        """Apply gamma correction and color boost - EXACT copy from working version"""
        gamma = 1.0 + (self.config_snapshot['gamma_level'] / 10) * 3.0  # 1.0–4.0
        boost = 1.0 + (self.config_snapshot['boost_level'] / 10) * 2.0  # 1.0–3.0
        
        rgb = np.array(rgb, dtype=float)
        # Gamma correction: linearize, boost, then de-linearize
        rgb_lin = np.power(rgb / 255.0, gamma)
        rgb_lin = np.clip(rgb_lin * boost, 0, 1)  # THIS WAS MISSING!
        rgb = np.power(rgb_lin, 1/gamma) * 255
        return tuple(rgb.astype(int))
    
    def extract_edge_colors(self, img, edge_type, count):
        """Extract colors from screen edges - EXACT copy from working version"""
        h, w = img.shape[:2]
        edge_colors = []
        
        # Use EDGE_AVG_PERCENT for the width/height of the strip sampled for each LED
        # THIS IS THE KEY FIX - different logic for top/bottom vs left/right
        if edge_type in ('top', 'bottom'):
            avg_size = max(1, int(self.config_snapshot['edge_avg_percent'] * h))
        else:
            avg_size = max(1, int(self.config_snapshot['edge_avg_percent'] * w))
            
        # For falloff, create weights (closer to edge = higher weight)
        falloff_exp = 0.01 + (0 / 10) * (0.25 - 0.01)  # Use same as working version
        
        if edge_type == 'top':
            strip = img[0:avg_size, :, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size)[::-1])  # 0=furthest, avg_size-1=closest
            weights = weights / np.sum(weights)
            cols = np.linspace(0, w, count + 1, dtype=int)
            for i in range(count):
                zone = strip[:, cols[i]:cols[i + 1], :]
                avg = np.tensordot(weights, zone, axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'right':
            strip = img[:, w-avg_size:w, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size)[::-1])
            weights = weights / np.sum(weights)
            rows = np.linspace(0, h, count + 1, dtype=int)
            for i in range(count):
                zone = strip[rows[i]:rows[i + 1], :, :]
                avg = np.tensordot(weights, zone.transpose(1,0,2), axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'bottom':
            strip = img[-avg_size:, :, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size))  # bottom: 0=closest, -1=furthest
            weights = weights / np.sum(weights)
            cols = np.linspace(0, w, count + 1, dtype=int)
            for i in range(count):
                zone = strip[:, cols[i]:cols[i + 1], :]
                avg = np.tensordot(weights, zone, axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'left':
            strip = img[:, 0:avg_size, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size))
            weights = weights / np.sum(weights)
            rows = np.linspace(0, h, count + 1, dtype=int)
            for i in range(count):
                zone = strip[rows[i]:rows[i + 1], :, :]
                avg = np.tensordot(weights, zone.transpose(1,0,2), axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        # Handle partial edges (for GUI flexibility)
        elif edge_type == 'bottom_left':
            strip = img[-avg_size:, :, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size))
            weights = weights / np.sum(weights)
            cols = np.linspace(0, w//2, count + 1, dtype=int)
            for i in range(count):
                zone = strip[:, cols[i]:cols[i + 1], :]
                avg = np.tensordot(weights, zone, axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'bottom_right':
            strip = img[-avg_size:, :, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size))
            weights = weights / np.sum(weights)
            cols = np.linspace(w//2, w, count + 1, dtype=int)
            for i in range(count):
                zone = strip[:, cols[i]:cols[i + 1], :]
                avg = np.tensordot(weights, zone, axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'top_left':
            strip = img[0:avg_size, :, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size)[::-1])
            weights = weights / np.sum(weights)
            cols = np.linspace(0, w//2, count + 1, dtype=int)
            for i in range(count):
                zone = strip[:, cols[i]:cols[i + 1], :]
                avg = np.tensordot(weights, zone, axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'top_right':
            strip = img[0:avg_size, :, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size)[::-1])
            weights = weights / np.sum(weights)
            cols = np.linspace(w//2, w, count + 1, dtype=int)
            for i in range(count):
                zone = strip[:, cols[i]:cols[i + 1], :]
                avg = np.tensordot(weights, zone, axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'left_top':
            strip = img[:, 0:avg_size, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size))
            weights = weights / np.sum(weights)
            rows = np.linspace(0, h//2, count + 1, dtype=int)
            for i in range(count):
                zone = strip[rows[i]:rows[i + 1], :, :]
                avg = np.tensordot(weights, zone.transpose(1,0,2), axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'left_bottom':
            strip = img[:, 0:avg_size, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size))
            weights = weights / np.sum(weights)
            rows = np.linspace(h//2, h, count + 1, dtype=int)
            for i in range(count):
                zone = strip[rows[i]:rows[i + 1], :, :]
                avg = np.tensordot(weights, zone.transpose(1,0,2), axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'right_top':
            strip = img[:, w-avg_size:w, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size)[::-1])
            weights = weights / np.sum(weights)
            rows = np.linspace(0, h//2, count + 1, dtype=int)
            for i in range(count):
                zone = strip[rows[i]:rows[i + 1], :, :]
                avg = np.tensordot(weights, zone.transpose(1,0,2), axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        elif edge_type == 'right_bottom':
            strip = img[:, w-avg_size:w, :3]
            weights = np.exp(-falloff_exp * np.arange(avg_size)[::-1])
            weights = weights / np.sum(weights)
            rows = np.linspace(h//2, h, count + 1, dtype=int)
            for i in range(count):
                zone = strip[rows[i]:rows[i + 1], :, :]
                avg = np.tensordot(weights, zone.transpose(1,0,2), axes=([0], [0])).mean(axis=0)
                edge_colors.append(self.enhance_color(avg))
        
        return edge_colors
    
    def get_led_colors_from_screen(self, img):
        """Map screen colors to LED positions - SIMPLIFIED like working version"""
        # Initialize all LEDs to black
        led_colors = [(0, 0, 0)] * self.config_snapshot['num_leds']
        
        # Current LED index (starting after the offset)  
        current_led = self.config_snapshot['led_start_offset']
        
        # Debug: Print image shape and initial LED index
        if hasattr(self, '_debug_counter') and self._debug_counter % 60 == 0:  # Every 2 seconds
            print(f"Debug: Image shape: {img.shape}, Starting LED: {current_led}")
        
        # Process each edge in the flow order - SIMPLE mapping like working version
        for edge_name, count, description, direction in self.led_segments:
            # Extract colors for this edge
            edge_colors = self.extract_edge_colors(img, edge_name, count)
            
            # Debug: Print edge info occasionally
            if hasattr(self, '_debug_counter') and self._debug_counter % 60 == 0:
                sample_color = edge_colors[0] if edge_colors else (0, 0, 0)
                print(f"Debug: {edge_name} -> {count} LEDs, sample color: {sample_color}, direction: {direction}")
            
            # Apply individual segment direction
            if direction == "reversed":
                edge_colors = edge_colors[::-1]
            
            # Assign colors to LEDs sequentially
            for i in range(count):
                if current_led < self.config_snapshot['num_leds']:
                    led_colors[current_led] = edge_colors[i]
                    current_led += 1
                else:
                    break  # Don't exceed total LED count
        
        # Debug: Print final LED assignment info
        if hasattr(self, '_debug_counter') and self._debug_counter % 60 == 0:
            active_leds = sum(1 for r, g, b in led_colors if r > 0 or g > 0 or b > 0)
            print(f"Debug: Final current_led: {current_led}, Active LEDs: {active_leds}")
        
        return led_colors
    
    def smooth_colors(self, prev, curr):
        """Apply exponential moving average smoothing"""
        if prev is None:
            return curr
        
        smoothing = min(max(self.config_snapshot['smoothing_level'] / 10 * 0.95, 0), 0.95)
        
        arr_prev = np.array(prev, dtype=float)
        arr_curr = np.array(curr, dtype=float)
        smoothed = arr_prev * smoothing + arr_curr * (1 - smoothing)
        return [tuple(map(int, c)) for c in smoothed]
    
    def send_wled_drgb(self, led_colors):
        """Send colors to WLED via UDP using the exact same method as ambilight_sync.py"""
        try:
            packet = bytearray()
            packet.append(2)  # DRGB protocol
            packet.append(2)  # Timeout (short, for high FPS)
            
            for r, g, b in led_colors:
                packet.extend([b, g, r])  # BGR order for WLED
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(packet, (self.config_snapshot['wled_ip'], self.config_snapshot['wled_port']))
            sock.close()
            
            # Debug output - reduced frequency
            if hasattr(self, '_debug_counter'):
                self._debug_counter += 1
            else:
                self._debug_counter = 1
                
            if self._debug_counter % 90 == 0:  # Debug every 3 seconds at 30fps
                active_leds = sum(1 for r, g, b in led_colors if r > 0 or g > 0 or b > 0)
                print(f"Sent packet: {len(packet)} bytes, {active_leds} active LEDs out of {len(led_colors)}")
                if active_leds > 0:
                    # Print first few active colors for debugging
                    active_colors = [(r, g, b) for r, g, b in led_colors if r > 0 or g > 0 or b > 0][:5]
                    print(f"Sample colors: {active_colors}")
            
        except Exception as e:
            print(f"Failed to send to WLED: {e}")
    
    def ambilight_worker(self):
        """Main ambilight processing loop - OPTIMIZED FOR 30+ FPS"""
        print("AMBILIGHT WORKER STARTED!")
        print(f"WLED IP: {self.config_snapshot['wled_ip']}, Port: {self.config_snapshot['wled_port']}")
        print(f"Monitor region: {self.monitor_region}")
        print(f"LED segments: {self.led_segments}")
        print(f"Number of segments: {len(self.led_segments) if self.led_segments else 0}")
        
        if not self.led_segments:
            print("ERROR: No LED segments configured!")
            return
        
        try:
            frame_count = 0
            start_time = time.time()
            last_fps_print = start_time
            
            print(f"Starting main loop with target 30+ FPS...")
            
            while self.ambilight_running:
                try:
                    frame_start = time.time()
                    
                    # Only debug first few frames
                    if frame_count < 3:
                        print(f"Frame {frame_count}: Capturing screen...")
                    
                    # Capture screen
                    with mss.mss() as sct:
                        monitor = {
                            'top': self.monitor_region[1],
                            'left': self.monitor_region[0],
                            'width': self.monitor_region[2],
                            'height': self.monitor_region[3]
                        }
                        img = np.array(sct.grab(monitor))
                    
                    if frame_count < 3:
                        print(f"Frame {frame_count}: Screen captured, shape: {img.shape}")
                    
                    # Process colors
                    led_colors = self.get_led_colors_from_screen(img)
                    if frame_count < 3:
                        print(f"Frame {frame_count}: Colors processed, {len(led_colors)} LEDs")
                    
                    led_colors = self.smooth_colors(self.prev_led_colors, led_colors)
                    self.prev_led_colors = led_colors
                    
                    # Send to WLED
                    self.send_wled_drgb(led_colors)
                    if frame_count < 3:
                        print(f"Frame {frame_count}: Sent to WLED")
                    
                    # Update frame counter
                    frame_count += 1
                    
                    # Print FPS every 3 seconds (instead of GUI update)
                    now = time.time()
                    if now - last_fps_print >= 3.0:
                        elapsed = now - start_time
                        fps = frame_count / elapsed
                        print(f"FPS: {fps:.1f}, Frame: {frame_count}")
                        last_fps_print = now
                    
                    # Target ~30 FPS - calculate sleep time
                    frame_time = time.time() - frame_start
                    target_frame_time = 1.0 / 30.0  # 33.33ms for 30 FPS
                    sleep_time = max(0, target_frame_time - frame_time)
                    
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                    
                except Exception as e:
                    print(f"Frame processing error: {e}")
                    import traceback
                    traceback.print_exc()
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"Ambilight worker error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.ambilight_running = False
            print("Ambilight worker stopped.")

    def toggle_ambilight(self):
        """Toggle ambilight on/off"""
        if self.ambilight_running:
            self.stop_ambilight()
        else:
            self.start_ambilight()

def main():
    root = tk.Tk()
    app = AmbilightConfigGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main() 