"""Simple test to verify DearPyGui can create a window."""

import sys
import dearpygui.dearpygui as dpg

print("Testing DearPyGui initialization...")

try:
    # Create context
    print("1. Creating context...")
    dpg.create_context()
    print("   ✓ Context created")

    # Create a simple window
    print("2. Creating window...")
    with dpg.window(label="Test Window", width=400, height=300):
        dpg.add_text("If you see this, DearPyGui works!")
        dpg.add_button(label="Close", callback=lambda: dpg.stop_dearpygui())
    print("   ✓ Window created")

    # Create viewport
    print("3. Creating viewport...")
    dpg.create_viewport(title="DearPyGui Test", width=500, height=400)
    print("   ✓ Viewport created")

    # Setup
    print("4. Setting up DearPyGui...")
    dpg.setup_dearpygui()
    print("   ✓ Setup complete")

    # Show viewport
    print("5. Showing viewport...")
    dpg.show_viewport()
    print("   ✓ Viewport shown")

    print("\n✓ GUI window should now be visible!")
    print("Close the window to exit.\n")

    # Render loop
    while dpg.is_dearpygui_running():
        dpg.render_dearpygui_frame()

    print("GUI closed successfully")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

finally:
    dpg.destroy_context()
    print("Cleanup complete")
