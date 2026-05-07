# IMR Salinity Sample Tracker — User Guide

This system manages the full lifecycle of water bottle salinity samples, from collection at sea to laboratory measurement and upload to the PhysChem database.

---

## Overview

```
Ship / CTD deck                   Lab
─────────────────                 ──────────────────────────────
1. Register sample           →    1. Scan QR label
   (BTL file or manual)           2. Measure & Enter salinity (PSAL_LAB)
2. Print label                    3. Upload to PhysChem
3. Take sample & attach label   
```

Every sample gets a **printed label** with a QR code. Scanning the QR code in the lab opens the measurement page directly — no tables, no searching.

---

## Part 1 — On the Ship: Registering Samples

Open the salinity tracker website in a browser. The address will be  `http://nautilus.imr.no:8000` for now and can only be reached inside the IMR network. 

### Option A — Upload a Seabird BTL File (recommended)

This is the fastest method. The BTL file is produced automatically by the Seabird SBE software after each CTD cast.

1. On the **home page**, click **📁 BTL File** (this tab is active by default).
2. Drag and drop the `.btl` file onto the drop zone, or click to browse. **One file (CTD cast) at a time.**
3. A preview table appears showing all bottles in the cast. Check that:
   - The cruise ID, station, platform name, and position look correct.
   - UTC time is filled in for each bottle. If it is missing, type it in before continuing.
   - PSAL sensor values (Sal00, Sal11) are populated.
4. Select the bottles you want to register using the checkboxes.
5. Click **Register Selected Bottles**.
6. Labels are generated automatically. Print them using the label printer.

> **Tip:** PSAL values from the CTD sensors are stored alongside the sample so the lab can compare their measurement against the instrument.

### Option B — Manual Entry

Use this for samples taken without a Seabird CTD (e.g. bucket samples, underway samples).

1. Click the **✏️ Manual Entry** tab.
2. Fill in:
   - **UTC Time** — date and time in 24-hour format (HH:MM).
   - **Latitude / Longitude** — decimal degrees (positive = N/E).
   - **Depth (m)** — collection depth.
   - **Platform** — vessel name (a suggestion list appears as you type).
   - **Cruise ID** — optional but strongly recommended; needed for automatic PhysChem matching.
   - Cast number, bottle number, PSAL sensor values — all optional.
3. Click **📝 Register & Generate Label**.

### Printing Labels

After registration the system shows a **View Label** link and a **Download Label PDF** button.

- The PDF is sized for the **Phomemo M110** label printer (50 × 30 mm).
- Each label shows: vessel, time, position, depth, bottle number (bold), and a QR code.
- Dry the sample bottle outside once it is filled with a towel or wipe
- Than immediately attach the label to the **dry** sample bottle before it leaves the CTD deck.

See **Appendix — Setting Up the Phomemo M110 on Windows** at the bottom of this guide for first-time printer setup.

![Phomemo M110 label printer](images/printer.png)
*Phomemo M110 connected via USB/CSBC.*

---

## Part 2 — In the Lab: Entering Measurements

### Step 1 — Get a PhysChem Token

Before you can upload measurements you need a token from the PhysChem authentication portal.

1. Open **https://physchem-token-test.hi.no** in a browser.
2. Log in with your institutional account.
3. Copy the token (a long string of letters and numbers).
4. On the measurement page, paste it into the **PhysChem token** box and click **Save token**.

The token is valid for **1 hour**. A live countdown is shown on every measurement page. When it expires, paste a new one.

> You only need to do this once per browser session (the token is stored in the server until it expires or you click **Clear**).

### Step 2 — Open the Measurement Page

Scan the QR code on the sample label with any phone or tablet. This opens the measurement page for that specific sample.

The page shows the sample metadata (time, position, depth, vessel) and the CTD sensor salinities for reference.

If a PhysChem token is active and the sample has a matching cruise in PhysChem, **existing PhysChem values** (CTD PSAL and any previous PSAL_LAB readings) are shown automatically so you can compare.

### Step 3 — Enter the Measurement

1. Type the measured salinity in the **PSAL_LAB** field.  
   Use the format `34.5796` (four decimal places recommended).
2. Optionally fill in **Measured by** (your name) and **Notes** (instrument used, any observations).
3. Click **📤 Upload Measurement**.

The system will:
- Save the measurement to the local database.
- Automatically find the matching PhysChem mission, CTD cast, and bottle by time, position, and depth.
- Upload the value as a new **PSAL_LAB** parameter with `acquirementMethod = 1020101`.

### Step 4 — Check the Result

**On success:** A summary page appears showing the uploaded value, CTD sensor PSAL values from PhysChem, and a **View in PhysChem →** link so you can verify the entry.

**On failure:** The error message is shown in red with details (e.g. "No BOT instrument found on operation 14252") and a direct link to the relevant PhysChem page so you can investigate. A **Retry** button lets you try again after fixing the issue.

### Adding a Second Measurement

If the same bottle is measured again (replicate, re-run), go back to the measurement page (scan the QR code again). A new **Add Additional Measurement** form is shown below the existing values. Submitting it creates a new PhysChem parameter with the next ordinal number (ordinal 2, 3, …) — the original value is never overwritten.

All measurements are listed in the **📋 Lab Measurements** table on the page, showing PSAL_LAB value, who measured it, when, and the PhysChem ordinal.

---

## Part 3 — Viewing and Exporting Samples

### Sample List

Go to **/samples** (or click the link on the home page) to see all registered samples with their status:

| Status | Meaning |
|--------|---------|
| `registered` | Label printed, bottle not yet in lab |
| `in_lab` | QR code scanned, measurement not yet entered |
| `measured` | Measurement entered but not yet uploaded to PhysChem |
| `uploaded` | Successfully uploaded to PhysChem |

You can filter by platform or status using the dropdowns.

### CSV Export

Click **⬇️ Download CSV** on the samples list page to download all sample data as a spreadsheet. The file includes all metadata, sensor values, lab measurements, and PhysChem upload IDs.

---

## Troubleshooting

### "PhysChem token not set"
Paste a fresh token from https://physchem-token-test.hi.no. Tokens expire after 1 hour.

### "No PhysChem mission found matching time/position"
- Check that the **Cruise ID** was entered during registration. Without it the system searches by time and position, which can fail if the cruise is not yet in PhysChem.
- Confirm the cruise has been created in PhysChem before uploading.

### "No BOT instrument found on operation XXXXX"
The matching CTD operation was found in PhysChem but it has no bottle (BOT) data. Ensure that the BTL file for this cast has been imported into PhysChem. Use the **View in PhysChem →** link in the error message to go directly to the operation and verify.

### "No matching CTD operation found"
The time or position of the sample does not match any operation in the PhysChem mission. Check that:
- The UTC time on the sample is correct.
- The correct cruise ID is stored with the sample.

### The QR code does not open the right page
The QR code URL is based on the server address configured at the time the label was printed. If the server address has changed, you can still find the sample by going to **/samples** and searching manually.

### Measurement page is slow to load
When a PhysChem token is active, the page fetches existing values from PhysChem on every load. This adds a few seconds. If PhysChem is unreachable, it times out silently and the page loads without the PhysChem section.

---

## Appendix — Setting Up the Phomemo M110 on Windows (USB/CSBC)

The M110 connects via a USB cable (CSBC port on the printer). Windows will install a generic USB serial driver automatically, but you need the **Phomemo printer driver** to set the correct label size.

### 1 — Install the Driver

1. Go to the Phomemo support page and download the Windows driver for the **M110**.  
   Search for "Phomemo M110 driver Windows" or check the CD/card that came with the printer.
2. Run the installer and follow the on-screen instructions.
3. Connect the M110 to the PC with the USB cable and power it on.
4. Windows should detect the printer and complete driver installation automatically.  
   If prompted, select **"Install driver automatically"**.

### 2 — Configure the Label Size (50 × 50 mm)

The driver defaults to a roll size that does not match our labels. You must set the correct size once.

1. Open **Settings → Bluetooth & devices → Printers & scanners**.
2. Click the **Phomemo M110** (or similar name) → **Printer preferences**.
3. In the preferences window, find the **Paper / Media** tab.
4. Set the paper size to **50 mm × 50 mm** (you may need to create a custom size):
   - Click **New** or **Custom paper size**.
   - Width: **50 mm**, Height: **50 mm**.
   - Save and apply.
5. Set **Orientation** to **Portrait**.
6. Click **OK** to save.

### 3 — Print a Label

1. Download the label PDF from the tracker (click **🖨️ Download Label PDF**).
2. Open the PDF in any PDF viewer (Adobe Acrobat, Microsoft Edge, Chrome, etc.).
3. Press **Ctrl + P** to print.
4. Select the **Phomemo M110** as the printer.
5. Under **Page sizing**, choose **Actual size** (do **not** select "fit to page" — this will shrink the label).
6. Click **Print**.

> **Tip:** If the printed label is too small or too large, re-check that the paper size in printer preferences is exactly 50 × 50 mm and that "Actual size" is selected in the print dialog.

### 4 — Loading Labels

- Use 50 mm wide continuous label roll.
- Open the printer cover, slide the roll in with the printable side facing down, and thread the paper through the slot until it comes out the front.
- Close the cover and press the feed button once to align the paper.

---

## Quick Reference

| Task | Where |
|------|-------|
| Register from BTL file | Home page → BTL File tab |
| Register manually | Home page → Manual Entry tab |
| View / print label | Sample measurement page → 🏷️ View Label |
| Enter measurement | Scan QR code on label |
| Get PhysChem token | https://physchem-token-test.hi.no |
| View all samples | /samples |
| Download CSV | /samples → ⬇️ Download CSV |
