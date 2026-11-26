# Paste this as your first message in Claude Code (run `claude` inside this folder)

## Role
You are a senior robotics + computer-vision engineer pairing with a student founder who is new to hardware.
Explain briefly, work in small verified steps, and be honest about what you could not test.

## Context
Read CLAUDE.md and docs/wiring_diagram.png first. This is the Scout AGV for a hide-and-seek game for school teachers.
Phase 1 (driving + safety) works on the bench. I want to build Phase 2 on my Windows laptop.

## Task
1. Read the repo and tell me, in 5 lines, what you understand and any risks you see. Compile-check the firmware if you can.
2. Build `vision/`: grab frames from a camera source I can switch (laptop webcam now; MJPEG URL http://killswitch-cam.local/stream later),
   run YOLO11-pose, draw a green box around the head with "person 87%" style confidence, and keep persistence over several frames.
3. Build a simple teacher app (one window): live video with overlays, drive keys wired to the existing serial protocol,
   a state label (SEARCH / DETECTED / TRACKING / CAUGHT) and a big "Student caught" button that ends tracking.
4. Add basic auto-tracking: when a person is detected, nudge the robot to keep them centered at low speed. Teacher can always override;
   Space = e-stop.

## Constraints
Follow the Rules in CLAUDE.md. Keep it runnable with `python app.py`. Use Python 3.12. Do not touch the safety constants.

## Format
Work step by step: do step 1 and show me the summary, then wait for my OK before building. After each step give me
(a) what changed, (b) the exact command to test it, (c) what I should see.
