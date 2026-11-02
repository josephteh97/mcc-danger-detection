# Corridor field test: step by step

What you do with the phone in a 1.8 × 2.5 m office corridor, from the stream to the report. It
checks the coverage maths (ρ = (f/p)/z, the square S and its centre d) with a real lens. The
detection sweep needs about 15 m and is not part of this test.

Settings used: phone stream 1280 × 720 (16:9), preset `corridor` (ρ 360 px/m, phone at 0.45 m),
A3 checkerboard with 10 × 7 squares (9 × 6 inner corners) of 36 mm.

## What you need

- The phone, on a mount that holds it still at about 0.45 m (a box or a chair seat works).
- The A3 checkerboard, taped flat on something rigid.
- A tape measure, and masking tape for floor marks (flat and easy to click; tissue moves).
- A 0.5 m stick or ruler (optional, for the density check).
- This PC on the same Wi-Fi as the phone, in the repo folder with the environment active.

## 0. Before you start

1. On the phone: open the RTSP camera app with **720p**, **H264**, **landscape**, port **1945**,
   and the login set. Press start. Keep the screen on and the app in front.
2. The stream URL, login included, is in `fieldtest/phone.local.yaml` (git-ignored, never
   commit it). `fieldtest/phone.yaml` has only a placeholder.
3. Check the stream:

   ```bash
   python3 -m tools.fieldtest probe
   ```

   Expected: `1280 × 720 at … fps` and a WARNING that the frame is 16:9. The warning is normal
   here: it means the lens must be calibrated at this size before the overlay works.

   If it says `cannot open` / `Connection refused`: the app isn't serving (start it again, screen
   on), or another viewer (ffplay, VLC) holds the stream. Close them and try again. The app
   restarts its server for a few seconds after a viewer leaves (for example right after `probe`),
   so the tool tries five times, 2 s apart, before giving up; the page also reconnects by itself if
   the stream drops during the test.

4. Start the page and open it in the browser:

   ```bash
   python3 -m tools.fieldtest serve --preset corridor
   ```

   Open http://127.0.0.1:8090. You see the live picture and, on the right, "Overlay off until the
   lens is calibrated at this size". Keep this terminal open for the whole test.

## 1. Calibrate the lens

Do this once per stream size. Don't change the app's resolution or zoom afterwards, or calibrate
again. The result is saved to `reports/fieldtest/calib_1280x720.json` and loaded every time the
page starts.

1. Put the phone on its mount. **Keep the phone still and move the board.**
2. Hold the board between about **0.6 m and 1.5 m** from the phone.
3. For each view: hold the board still for a second (the stream is slow, and a moving board blurs),
   then press **Capture checkerboard**. The page counts the views.
   - All 54 inner corners must be in the picture. If a square at the edge is cut off, the page
     says "no checkerboard in this frame" and the view is not counted. Move it in a little.
   - Bright glare on the black squares also spoils it: tilt the board slightly.
4. Take **15–20 views**, covering:

   | Where | How many |
   |---|---|
   | Middle of the frame, flat on | 2–3 |
   | Each of the four corners of the frame | 1–2 each |
   | Along the left, right, top and bottom edges | 1 each |
   | Tilted about 30–45° left, right, up and down | 4–6 |
   | Near (0.6 m) and far (1.5 m) | 2–3 each |

   The corners and edges matter most: that's where the lens bends straight lines.
5. Press **Calibrate**.

**Result** (shown in the panel on the right):

- `lens: PASS` when the reprojection error is **0.5 px or less**.
- `f/p … (nominal 850.4, …%)`: the measured fx against the phone's published lens. A few percent
  off is normal.
- The overlay switches on.

**If it fails:**

| Message or result | What to do |
|---|---|
| "N checkerboard views found; at least 12 are needed" | Capture more views. |
| Reprojection over 0.5 px | Restart the page (the captured views are cleared) and capture again: board flatter, held stiller, more views in the corners. |
| fx far from 850 (more than about 10%) | Check `square_mm` is 36 in `fieldtest/phone.yaml`, that the app is at 720p and zoom 1×, then calibrate again. |

The views are kept only while the page runs: restarting the page starts the count again. A saved
calibration stays.

**Working alone: calibrate from a recording.** No need to hold the board and press Capture at once.

1. Lean the board against a wall or chair, flat and still. Stop the page (Ctrl+C) if it runs.
2. Start a recording and move the **phone** slowly around the board for a minute, pausing a moment
   at each spot: board in the middle, in each corner of the picture, along the edges, tilted
   left, right, up and down, near (0.6 m) and far (1.5 m):

   ```bash
   python3 -m tools.fieldtest record --seconds 60
   ```

3. Calibrate from it (every 10th frame; blurred frames without the board are skipped):

   ```bash
   python3 -m tools.fieldtest calibrate --file reports/fieldtest/<date>/rec_<time>.mp4 --every 10
   ```

   It prints the reprojection (PASS at 0.5 px or less) and fx against the nominal 850 px, and
   saves the same `calib_1280x720.json` the page loads. With fewer than 12 board views found,
   use `--every 5` or record again more slowly.
4. Delete the recording afterwards if it shows people.

**Moving the phone after calibrating is fine:** the calibration describes the lens, not where the
phone stands; the markers give the new position. Keep the same resolution (720p), zoom 1×, main
camera, landscape the same way round and stabilisation off. If any of these changes, calibrate
again.

## 2. Mark the floor

Use the tape measure, not the screen: the marks are the true positions, and the screen is
what's being tested. Print the positions any time with
`python3 -m tools.fieldtest zone --preset corridor`.

1. Mark the **origin** (0, 0): the spot on the floor directly under the phone's lens, at one end
   of the corridor.
2. Mark a straight line from it down the middle of the corridor: that's **y** (ahead). **x** is
   to the right, looking along the line.
3. Mark these five points (metres):

   | Marker | x (right) | y (ahead) |
   |---|---|---|
   | far left | −0.71 | 2.36 |
   | far right | +0.71 | 2.36 |
   | near right | +0.71 | 0.94 |
   | near left | −0.71 | 0.94 |
   | centre | 0 | 1.65 |

   The four corners make the square S = 1.42 m, from z_near 0.94 m to z_far 2.36 m, with its
   centre at d = 1.65 m. Use small tape crosses and click their middle later.

## 3. Set up the phone

1. Put the phone's lens **directly over the origin**. The tool draws the square from where the
   phone really is, so an offset phone gives a shifted square.
2. Turn the phone so the **centre marker is in the left–right middle of the picture** (u ≈ 640
   px). Then the phone looks straight along the line. Up–down position doesn't matter as long as
   all five markers are in the picture.
3. **Measure the lens height** from the floor. If it isn't 0.45 m, type it into **taped height**
   on the page and press **Apply**.
4. Don't touch the phone from now on.

## 4. Click the markers

1. Press **Cone**.
2. For each marker:
   1. Type its **x** and **y** in the boxes (they keep the last values: change them every time).
   2. Pick its **name** from the list (far left, far right, near right, near left). The centre
      marker has no name: leave it blank.
   3. Click the **middle of the marker** on the picture.
3. A wrong click: press **Undo cone** and click it again.
4. After four markers the panel shows the pose: `height … m pitch … roll … heading … reproj … px`.
   Click the centre marker too: five markers give a better pose.

## 5. Check the results

In the panel on the right:

| Step | PASS when |
|---|---|
| lens | reprojection 0.5 px or less |
| pose | solved height within 5 cm of the taped height **and** every marker within 2 px of where the pose puts it |
| overlay | each named corner of the green square within 2% of the frame width (about 26 px) of its marker |

Look at the picture too: the green square should sit on your four corner markers, with its centre
cross on the centre marker.

**If pose or overlay fails:**

- Check each marker's x and y on the floor with the tape, and that each was typed and named right
  (the panel lists the clicked cones).
- Check the phone hasn't moved since you clicked.
- Undo the cones and click them again, zooming the browser in to click more precisely.

## 6. Density check (optional)

This checks ρ: how many pixels a known length takes at a known distance.

1. Stand the 0.5 m stick upright on a marker (for example the centre).
2. Press **Measure**, set **length** to `0.5` and a **label** (for example `centre`).
3. Click the stick's **base**, then its **top**.
4. The panel shows predicted against measured pixels. PASS is within 5% (or 1 px for anything
   under 20 px).

Repeat on the near and far markers. A 1 m pole near the phone is taller than the picture: use the
0.5 m stick.

## 7. Write the report

Press **Write report**. It saves to `reports/fieldtest/<date>/`:

- `report.md`: every step and its PASS/FAIL, the lens, the pose, S, d, z_near, z_far, the
  square's bounding box in the picture and the measurements.
- `overlay.png`: the picture with the square drawn on it.
- `measurements.csv`, `layout.txt`, and `session.json` with every click.

Print the numbers from the saved session at any time:

```bash
python3 -m tools.fieldtest zone --session reports/fieldtest/<date>/session.json
```

This gives S, d, z_near, z_far and the square's bounding box in the picture, using the calibrated
lens and the solved pose.

`reports/` is git-ignored. If a recording shows people, delete it after the test.
