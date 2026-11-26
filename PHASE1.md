# Scout AGV — Phase 1: remote drive + safety

## Wiring changes from the gimbal build
- PCA9685 **CH0 = LEFT wheel servo, CH1 = RIGHT wheel servo** (your two continuous MG996Rs).
- **D8 -> PCA9685 OE is now required.** It is the hardware cut that stops all motor pulses on e-stop / deadman.
- Remove the laser branch (2N2222, 1k, 10k, interlock, KY-008). Leave the rest as it is.
- Motor power still goes ONLY to the PCA9685 V+ terminal. Uno 5V still feeds only PCA9685 VCC.
- Optional: HC-SR04 at the front: VCC->5V, GND->GND, TRIG->D9, ECHO->D10, then set `USE_ULTRASONIC 1`.

## Steps
1. **Wheels OFF the ground** (robot on a block). Upload `agv_drive.ino`. Serial Monitor 115200, Newline.
   Expect `OK BOOT killswitch-agv-drive v1.0 pwm=ok`.
2. **Neutral trim.** Send `M1*7C` (expect `OK M1`), then `V0,0`. Both wheels must be perfectly still.
   If one creeps, change its `NEUTRAL_US_...` (e.g. 1490 or 1510), re-upload, repeat.
3. **Direction.** Send `V15,15`: both wheels must turn the "forward" way. If one is backwards, flip its `INVERT_...`.
   Then `V15,-15` should spin the robot in place.
   **Shortcut for steps 4-6:** close the Serial Monitor and run `python bench_test.py --port COMx`. It checks all three and prints PASS/FAIL.
4. **Deadman.** Send `V15,15` once and stop typing: both wheels stop within ~250 ms and `ERR E07` appears.
5. **E-stop.** Arm, `V15,15`, then `Z`: stops at once. `V15,15` now returns `ERR E08` until you send `M1*7C`.
6. **Speed cap.** `V100,100` must run at the 30 % cap, not full speed.
7. Close the Serial Monitor. Install: `pip install pyserial pygame`, then `python teleop.py --port COMx`.
   W/S/A/D to drive, 1/2/3 speed, SPACE e-stop, R re-arm, ESC quit. Wheels still off the ground.
8. Pull the USB cable while driving: the motors stop (deadman) as soon as the Uno loses the host.
   (If the Uno itself loses power, outputs go dead; the PCA9685 may keep the last pulse until its own power drops, so always have a physical power switch.)
9. Only then put the robot on the floor. Start at speed level 1.

## Phase 1 is done when
- Neutral is still, directions are right, cap holds (steps 2-6).
- Deadman stops within ~250 ms (step 4) and e-stop latches (step 5).
- You can drive the robot around a room with the keyboard.
- (If the sensor is fitted) the robot stops before a wall when driven straight at it slowly.

## Known limits
- Firmware was **not compiled or run on hardware** by me; expect to fix small things on first upload.
- No wheel encoders: speed is open loop and varies with battery and floor.
- Always keep a physical power switch on the motor supply.
