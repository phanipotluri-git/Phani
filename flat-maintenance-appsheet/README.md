# Flat Maintenance Transparency App (AppSheet)

An AppSheet app for a building with **5 flats + 1 common area** where every flat
owner can see, at any time:

- who paid this month's maintenance and who hasn't,
- every rupee spent (watchman salary, power bill, water, repairs…) with the bill photo,
- the money left in the fund, month by month.

The data lives in a Google Sheet. Start from `FlatMaintenance_Template.xlsx` in this folder.

---

## 1. What the app can do

| Feature | What owners see | Who can change it |
|---|---|---|
| **Dashboard** | Fund balance now, this month's collection vs spend, list of unpaid flats | — (computed) |
| **Collections** | Every payment: flat, month, amount, UPI ref, screenshot | Owner submits "I paid" + screenshot → Treasurer verifies |
| **Expenses** | Every payment from the fund, with category and bill/receipt photo | Treasurer (Admin) only |
| **Monthly statement** | Opening balance, collected, spent, closing balance for each month | — (computed) |
| **My dues** | Each owner sees their own pending months | — (computed) |
| **Requests** | Complaints / work for the common area (bulb fused, motor issue) and their status | Anyone raises; Admin closes |
| **Auto e-mails** | Reminder to unpaid flats, alert when an expense is added, month-end PDF statement to everyone | Automatic |

Transparency rules built into the design:

1. **Everyone can read everything**; only the Admin/Treasurer edits money records.
2. **No deletes.** A mistake is fixed by a correcting entry, so history can't vanish.
3. Every row stores **RecordedBy** (e-mail) and **RecordedAt** (timestamp) automatically.
4. Every expense should have a **bill photo** (made required for amounts above, say, ₹500).
5. Past months can be **Locked** so they can't be edited after the statement is sent.

---

## 2. Google Sheet structure (the template)

Upload `FlatMaintenance_Template.xlsx` to Google Drive → *Open with Google Sheets* →
*File → Save as Google Sheets*. Replace the sample names/e-mails with real ones.

| Tab | Columns | Notes |
|---|---|---|
| **Flats** | FlatID, FlatNo, OwnerName, OwnerEmail, Phone, MonthlyMaintenance, Role | Role = `Admin` (treasurer) or `Owner` |
| **Months** | MonthID (`2026-11`), MonthStart, OpeningBalance, Locked | OpeningBalance only on the first month (cash already in hand) |
| **Categories** | Category, Kind, BudgetPerMonth | Watchman Salary, Common Area Power, Water, Cleaning, Repairs… |
| **Collections** | CollectionID, Month, Flat, Amount, PaidOn, Mode, TxnRef, ProofPhoto, Status, RecordedBy, RecordedAt, Notes | Status = `Pending` / `Verified` / `Rejected` |
| **Expenses** | ExpenseID, Month, ExpenseDate, Category, Description, Amount, PaidTo, Mode, BillPhoto, RecordedBy, RecordedAt | |
| **Requests** | RequestID, RaisedBy, RaisedAt, Title, Details, Photo, Status, Resolution | Status = `Open` / `In progress` / `Done` |

Sample data check: October opening ₹5,000 + collected ₹10,000 − spent ₹8,980 = **₹6,020** closing.

---

## 3. Build it in AppSheet (step by step)

1. Go to **appsheet.com** → *Create → App → Start with existing data* → pick the Google Sheet.
2. *Data → Tables → Add table* for each tab (Flats, Months, Categories, Collections, Expenses, Requests).
3. Set the column types below (*Data → Columns*).

### Column types

**Flats**: FlatID = Key, Text · OwnerEmail = Email · MonthlyMaintenance = Price · Role = Enum (`Admin`, `Owner`)

**Months**: MonthID = Key, Text · MonthStart = Date · OpeningBalance = Price · Locked = Yes/No

**Categories**: Category = Key · Kind = Enum · BudgetPerMonth = Price

**Collections**
| Column | Type | Initial value / setting |
|---|---|---|
| CollectionID | Text, Key | `UNIQUEID()` |
| Month | Ref → Months | `TEXT(TODAY(), "YYYY-MM")` |
| Flat | Ref → Flats | `ANY(SELECT(Flats[FlatID], [OwnerEmail] = USEREMAIL()))` |
| Amount | Price | `[Flat].[MonthlyMaintenance]` |
| PaidOn | Date | `TODAY()` |
| Mode | Enum | `UPI`, `Cash`, `Bank`, `Cheque` |
| ProofPhoto | Image | |
| Status | Enum | `"Pending"`; *Editable_If*: `LOOKUP(USEREMAIL(), "Flats", "OwnerEmail", "Role") = "Admin"` |
| RecordedBy | Email | `USEREMAIL()`, Editable = off |
| RecordedAt | DateTime | `NOW()`, Editable = off |

**Expenses**
| Column | Type | Initial value / setting |
|---|---|---|
| ExpenseID | Text, Key | `UNIQUEID()` |
| Month | Ref → Months | `TEXT([ExpenseDate], "YYYY-MM")` |
| ExpenseDate | Date | `TODAY()` |
| Category | Ref → Categories | |
| Amount | Price | |
| BillPhoto | Image | *Required_If*: `[Amount] > 500` |
| RecordedBy / RecordedAt | Email / DateTime | `USEREMAIL()` / `NOW()`, not editable |

**Requests**: RequestID = `UNIQUEID()`, RaisedBy = `USEREMAIL()`, RaisedAt = `NOW()`, Status = Enum, Photo = Image.

### Virtual columns (the "transparency math")

Add these with *Data → Columns → Add virtual column*.

**On Months**
```
Collected      = SUM(SELECT(Collections[Amount], AND([Month] = [_THISROW].[MonthID], [Status] = "Verified")))
Spent          = SUM(SELECT(Expenses[Amount], [Month] = [_THISROW].[MonthID]))
ClosingBalance = SUM(SELECT(Months[OpeningBalance], [MonthID] <= [_THISROW].[MonthID]))
               + SUM(SELECT(Collections[Amount], AND([Month] <= [_THISROW].[MonthID], [Status] = "Verified")))
               - SUM(SELECT(Expenses[Amount], [Month] <= [_THISROW].[MonthID]))
OpeningCalc    = [ClosingBalance] - [Collected] + [Spent]
PaidFlats      = SELECT(Collections[Flat], AND([Month] = [_THISROW].[MonthID], [Status] = "Verified"))
UnpaidFlats    = Flats[FlatID] - [PaidFlats]
```
(`MonthID` is text like `2026-11`, so `<=` compares months correctly.)

**On Flats**
```
TotalPaid     = SUM(SELECT(Collections[Amount], AND([Flat] = [_THISROW].[FlatID], [Status] = "Verified")))
PaidThisMonth = IN([FlatID], SELECT(Collections[Flat], AND([Month] = TEXT(TODAY(), "YYYY-MM"), [Status] = "Verified")))
PendingMonths = COUNT(Months[MonthID]) - COUNT(SELECT(Collections[CollectionID], AND([Flat] = [_THISROW].[FlatID], [Status] = "Verified")))
```

**On Categories**
```
SpentThisMonth = SUM(SELECT(Expenses[Amount], AND([Category] = [_THISROW].[Category], [Month] = TEXT(TODAY(), "YYYY-MM"))))
```

### Security (who can do what)

- *Security → Require sign-in*: **On**. Add the 5 owner e-mails under *Users / Share*.
- *Security → Security filter* on **Flats**: `IN(USEREMAIL(), Flats[OwnerEmail])` (only members get data).
- *Data → Tables → Expenses → Are updates allowed?* → expression:
  ```
  IF(LOOKUP(USEREMAIL(), "Flats", "OwnerEmail", "Role") = "Admin", "ADDS_AND_UPDATES", "READ_ONLY")
  ```
- **Collections** → `ADDS_AND_UPDATES` for everyone (owners can submit their payment);
  Status is admin-only through the *Editable_If* above.
- **Months / Categories / Flats** → same Admin-only expression as Expenses.
- Never choose `ALL_CHANGES` → nobody can delete records.
- Lock old months: on Collections and Expenses set *Editable_If* of each column to `NOT([Month].[Locked])`.

### Views (UX → Views)

| View | Type | Data | Tip |
|---|---|---|---|
| Dashboard | Dashboard | Current month card + Unpaid flats + Spend chart | Main screen |
| This Month | Detail | Months, filtered to current month (slice `[MonthID] = TEXT(TODAY(),"YYYY-MM")`) | Shows Collected / Spent / ClosingBalance |
| Statements | Table | Months, sorted descending | Tap a month for details |
| Collections | Deck | Collections, grouped by Month | Show ProofPhoto as image |
| Expenses | Deck / Gallery | Expenses, grouped by Month then Category | Bill photo as main image |
| Spend by category | Chart (Pie) | Expenses (current-month slice) | |
| Pending verification | Table | Slice `[Status] = "Pending"` | Show only to Admin: *Show_If* `LOOKUP(USEREMAIL(),"Flats","OwnerEmail","Role")="Admin"` |
| My Flat | Detail | Flats slice `[OwnerEmail] = USEREMAIL()` | Own dues & history |
| Requests | Table | Requests | |

**Action for the treasurer**: *Behavior → Actions → "Verify"* on Collections:
set `Status = "Verified"`, *Only if*: `AND([Status] = "Pending", LOOKUP(USEREMAIL(),"Flats","OwnerEmail","Role") = "Admin")`.

### Automations (Automation → Bots)

1. **Monthly reminder** – Schedule: 5th of every month, 9 AM. For each row in Flats where
   `NOT([PaidThisMonth])` → send e-mail to `[OwnerEmail]`: "Maintenance of ₹<<[MonthlyMaintenance]>> for <<TEXT(TODAY(),"MMMM YYYY")>> is pending."
2. **New expense alert** – Event: Expenses *Adds only* → e-mail all owners
   (`Flats[OwnerEmail]`): "₹<<[Amount]>> spent on <<[Category]>> – <<[Description]>>" with the bill photo.
3. **Payment verified** – Event: Collections *Updates* where `[Status] = "Verified"` → e-mail the
   flat owner a receipt.
4. **Month-end statement** – Schedule: 1st of every month → *Create a new file* (PDF from a
   Google Doc template with the previous month's Collected / Spent / Closing and the expense list)
   and e-mail it to all owners. Then set that month's `Locked = TRUE`.
5. *(Optional)* **Auto-create next month** – Schedule: 1st of month → add a row to Months with
   `MonthID = TEXT(TODAY(),"YYYY-MM")`.

---

## 4. Day-to-day workflow

1. **Owner pays** the treasurer via UPI → opens app → *Collections → +* → month and amount are
   pre-filled → attach screenshot → Save (Status = Pending).
2. **Treasurer** opens *Pending verification* → checks bank/UPI → taps **Verify**.
3. **Treasurer pays** watchman / power bill → *Expenses → +* → category, amount, photo of the bill.
   All owners get an e-mail immediately.
4. **Anyone, anytime** opens the Dashboard to see balance, unpaid flats and spending.
5. On the 1st, everyone gets the PDF statement of the previous month automatically.

---

## 5. Ideas for later

- **Reserve / corpus fund** – a separate category or table for big future costs (painting, motor replacement) with its own target.
- **Budget vs actual** – compare `SpentThisMonth` with `BudgetPerMonth` and highlight overspend in red (*UX → Format rules*).
- **Late fee** – virtual column that adds a penalty after the 10th.
- **Rotating treasurer** – change the `Role` in the Flats sheet; no app change needed.
- **Polls / approvals** – an Approvals table for expenses above ₹5,000 where at least 3 of 5 owners must tap "Approve" before the treasurer pays.
- **Vendor list** – watchman, plumber, electrician phone numbers in a Contacts table with call buttons.
- **Shared bank/UPI account** – use a separate bank account for the association so the bank statement matches the app.

---

## 6. Cost and limits (check current AppSheet pricing)

- AppSheet is free while the app is a **prototype** with up to **10 test users**, which covers
  5 flats. Some features (certain automations, e-mail to non-creator users, PDF generation) may
  require a paid plan; if you have Google Workspace, AppSheet Core may already be included.
- The Google Sheet is the source of truth: share it **view-only** with owners as a backup view,
  and keep edit access with the Admin only, so nobody can bypass the app's rules.
