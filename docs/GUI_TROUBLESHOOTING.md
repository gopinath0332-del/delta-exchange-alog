"""
GUI Launch Troubleshooting Guide
=================================

If you're experiencing issues launching the GUI, this is likely due to one of the following:

## Common Issues

### 1. Segmentation Fault on macOS

**Symptom**: Application crashes immediately with "segmentation fault"

**Cause**: DearPyGui requires OpenGL and may have compatibility issues with certain macOS configurations, especially:

- Running via SSH without display
- Certain macOS versions or graphics drivers
- Virtual machines or containers

**Solutions**:
a) Ensure you're running on a Mac with an active display (not via SSH)
b) Try updating macOS and graphics drivers
c) Use terminal mode instead (see below)

### 2. No Display Available

**Symptom**: "No display available" error message

**Cause**: Running in a headless environment

**Solutions**:
a) Run on a system with a display
b) Use SSH with X11 forwarding: `ssh -X user@host`
c) Use terminal mode instead

### 3. OpenGL Errors

**Symptom**: OpenGL-related error messages

**Cause**: Missing or incompatible OpenGL drivers

**Solutions**:
a) Update graphics drivers
b) Ensure OpenGL 3.3+ is supported
c) Use terminal mode instead

## Alternative: Terminal Mode

The application fully supports terminal mode for all operations:

### Fetch Market Data

```bash
python3 main.py fetch-data --symbol BTCUSD --timeframe 1h --days 30
```

### Run Backtest

```bash
python3 main.py backtest --strategy moving_average --symbol BTCUSD
```

### Start Live Trading (Paper Mode)

```bash
python3 main.py live --strategy rsi --symbol BTCUSD --paper
```

### Generate Report

```bash
python3 main.py report --backtest-id latest --output report.pdf
```

## System Requirements for GUI

- **Operating System**: macOS 10.14+, Windows 10+, or Linux with X11
- **Graphics**: OpenGL 3.3+ support
- **Display**: Active display (not headless)
- **Python**: 3.9+
- **Dependencies**: DearPyGui 1.10.0+

## Reporting Issues

If you continue to experience issues:

1. Check the logs in `logs/trading.log`
2. Verify DearPyGui installation: `pip show dearpygui`
3. Test DearPyGui directly:
   ```python
   import dearpygui.dearpygui as dpg
   dpg.create_context()
   print("DearPyGui works!")
   ```

## Contact

For further assistance, please refer to:

- Delta Exchange API Docs: https://docs.delta.exchange/
- DearPyGui Documentation: https://dearpygui.readthedocs.io/
