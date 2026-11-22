# Shipping & Receiving Implementation Plan (PRD)

*Scope: outbound FedEx Ground and inbound DHL imports in the ilLumenate ERPNext instance. Status: decisions made (EasyPost, button-driven labels, no dealer-billed freight). Phases 1 to 3 built (see section 12). Updated 2026-11-22.*

How the built part works, the ERPNext to n8n contract and the setup steps: `SHIPPING_EASYPOST_INTEGRATION.md`.

## 1. Goals

1. Capture package dimensions and weight once and reuse them for labels, quotes and reporting.
2. Buy FedEx Ground labels through EasyPost from a button, with tracking written back automatically.
3. Support multi-box orders and split shipments cleanly.
4. Give dealers accurate, multi-package tracking in the portal and emails.
5. Track DHL imports end to end through landed cost.

**Non-goals:** replacing the Quote to Delivery Note flow, building a full TMS, international outbound by DHL, and collect or third-party-billed freight (all outbound freight is billed to our FedEx account).

## 2. Decisions made

| Topic | Decision |
| --- | --- |
| Label provider | **EasyPost**, with our own FedEx account connected so we get our negotiated rates |
| Label purchase | **Button only** (Create Labels on the Shipment). No automatic purchase on submit |
| Customer-billed freight | **Not supported.** All freight is billed to us and recovered, if at all, through a shipping charge on the order |
| Package data | Native Shipment and Shipment Parcel |
| Units | Inches and pounds in ERPNext. The n8n workflow converts pounds to ounces for EasyPost |
| Inbound | Keep ilL Inbound Shipment |

**Working assumption, not yet confirmed:** invoice per Delivery Note (each ship event is billed when it ships). Change this if finance wants one invoice at the end of the order.

## 3. Current state

Checked against the live site and the repo.

**Already in place**

- Delivery Note custom fields `ill_carrier` (UPS, FedEx, USPS, Freight, Other) and `ill_tracking_number`, plus the legacy `transporter_name`, `vehicle_no` and `lr_no` fallbacks.
- `portal/shipment_tracking.py` returns **one** carrier, number and URL per Delivery Note. It is used by the portal order page and the shipment emails. The print formats (`ill_delivery_note`, `ill_packing_list`) read `ill_tracking_number` directly, and the command center gateway only exposes `ill_carrier` / `ill_tracking_number` for editing.
- A shipment email hook runs on Delivery Note submit.
- `ilL Inbound Shipment` with freight mode, forwarder (already a link to Supplier), customs broker (link to Supplier), incoterm, tracking, ETD/ETA, customs entry, PO and receipt links, estimated and actual costs, and Landed Cost Voucher links.
- Item has `weight_per_unit`, `weight_uom`, `country_of_origin` and `customs_tariff_number`.

**Native ERPNext Shipment doctype (verified on the instance)**

- Submittable. Statuses: Draft, Submitted, Booked, Cancelled, Completed. Tracking statuses: In Progress, Delivered, Returned, Lost.
- `shipment_parcel` child table with length, width, height, weight and count. It has no unit fields.
- `shipment_delivery_note` child table (Delivery Note link and grand total). One Shipment can list several Delivery Notes.
- Carrier fields: `carrier`, `carrier_service`, `awb_number`, `tracking_url`, `service_provider`, `shipment_id`, `shipment_amount`.
- **Required on every Shipment:** pickup address, delivery address, value of goods, pickup date, pickup from/to times, description of content. These need defaults or the process will feel heavy.
- Parcel Templates exist for box presets.

**Empty today:** there are no Shipment records, no Parcel Templates and no custom fields on Shipment or Shipment Parcel. This is a clean start.

**Gaps**

- No dimensions on Item (standard Item has weight only).
- No label purchase or tracking status updates.
- The tracking helper cannot show more than one number.
- DHL is not a carrier option, and Inbound Shipment tracking is manual.

## 4. Design decisions

| Decision | Choice | Why |
| --- | --- | --- |
| Where package data lives | Native **Shipment** and **Shipment Parcel** | Avoids a parallel custom table and upgrade friction |
| Shipment to Delivery Note | **One Shipment per Delivery Note** (a Shipment may list more than one only by exception) | Keeps packing list, tracking and invoice aligned |
| Split orders | Separate Delivery Notes per ship event or carrier | Standard ERPNext behavior and matches production timing |
| Label buying | **Create Labels button** on the Shipment calls an **n8n workflow**, which calls **EasyPost** | n8n is already connected, and the native ERPNext carrier integrations do not cover FedEx |
| Tracking source of truth | Shipment records. `ill_tracking_number` on Delivery Note stays as a mirror of the primary number | Portal and emails keep working during migration |
| Units | Inches and pounds in ERPNext, ounces sent to EasyPost | Shipment Parcel has no unit field, and EasyPost takes weight in ounces |
| Inbound | Keep **ilL Inbound Shipment** | Native Shipment is outbound oriented |

## 5. Data model changes

**Custom fields (kept to the minimum)**

| Doctype | Field | Purpose | Phase |
| --- | --- | --- | --- |
| Shipment Parcel | `ill_tracking_number` (Data) | Per-box FedEx tracking number | 2 |
| Shipment Parcel | `ill_special_handling` (Check) | Oversize or additional handling flag, set from the thresholds | 2 |
| Shipment Parcel | `ill_tracking_status` (Data) | Per-box tracker status, so the Shipment is Delivered only when every box is | 3 |
| Shipment Parcel | `ill_label_url` (Data) | Per-box label PDF from EasyPost | 2 |
| Shipment | `ill_label_status` (Select: Not bought, Bought, Voided, Error) | Drives the buttons and error display | 2 |
| Shipment | `ill_label_message` (Small Text) | Last label error, shown on the form | 2 |
| Shipment | `ill_label_url` (Attach or Data) | Label PDF link | 2 |
| Shipment | `ill_easypost_shipment_id` (Data) | EasyPost shipment ID, needed to void, re-print and match tracker webhooks | 2 |
| Item | `ill_length_in`, `ill_width_in`, `ill_height_in`, `ill_units_per_carton` | Optional estimate and pre-fill | 5 |
| Sales Order Item | `ill_ship_weight_lb`, `ill_ship_length_in` | Configurator computed estimate | 5 |

Delivery tracking status uses the native `tracking_status` field on Shipment, so no extra status field is needed.

Custom fields on standard doctypes carry the `ill_` prefix (repo convention, avoids clashes with future ERPNext fields).

**Records to create:** Parcel Templates (our standard boxes), a default shipping Address for the warehouse, and ilL-Shipping-Settings (webhook, secret, carrier account, pickup defaults, surcharge thresholds).

## 6. Target workflows

### Outbound

1. Sales Order to Pick List to Delivery Note (unchanged).
2. On the Delivery Note, a **Create Shipment** button builds a Shipment with the following defaults:
   - Pickup address is the warehouse address.
   - Delivery address is the Delivery Note shipping address.
   - Value of goods is the Delivery Note total.
   - Pickup date is today and the window is the default pickup window.
   - Description of content is a default such as "LED lighting fixtures and components".
   - Parcel rows are pre-filled by a suggested split based on Item weight and units per carton, when available.
3. Staff pick a Parcel Template or enter dimensions, then enter the scale weight.
4. Staff click **Create Labels** on the Shipment. ERPNext sends the parcels to n8n, and n8n calls EasyPost:
   - verify the delivery address,
   - create the EasyPost shipment with each parcel (inches, ounces),
   - select FedEx Ground on our connected FedEx account, and buy it,
   - write back the master tracking number to `awb_number`, per-box numbers to the parcel rows, the tracking URL, the label PDF as an attachment, `ill_easypost_shipment_id`, `ill_label_status`, and the cost to `shipment_amount`.
5. A hook mirrors the primary tracking number and carrier to the Delivery Note (`ill_carrier`, `ill_tracking_number`).
6. Delivery Note submit sends the dealer email as it does today.
7. EasyPost tracker webhooks reach an n8n webhook, which updates `tracking_status` and completes the Shipment on delivery.
8. **Void Label** button requests an EasyPost refund and sets `ill_label_status` to Voided.

### Inbound (DHL)

1. Purchasing creates the Inbound Shipment with the waybill number, incoterm and ETA. The tracking URL builds from the waybill.
2. DHL tracking updates ATA, status and delivered date. The same EasyPost tracker service can follow DHL waybills, so a scheduled or webhook-driven n8n workflow can update open Inbound Shipments without a second integration. Confirm that EasyPost tracks our DHL service type in Phase 0.
3. Receiving creates the Purchase Receipt and links it.
4. Accounting enters the DHL freight and duty invoices and creates the Landed Cost Voucher. The purchasing board flags late shipments.

## 7. Phases and requirements

### Phase 0: Spike and setup (about 2 to 3 days)

- Test the native Shipment on a **staging copy, not production**: one Delivery Note in two Shipments, submit and cancel behavior, whether submit requires parcels, and what the Delivery Note shows after linking.
- Create the EasyPost account, connect our FedEx account, and get test-mode and production API keys. Add them as n8n credentials. Set up the tracker webhook URL.
- Confirm current EasyPost pricing and FedEx Ground service names with EasyPost.
- Collect the box list, pickup schedule and surcharge rules from the shipping lead.
- Create Parcel Templates and the warehouse Address.
- **Exit:** a hand-made Shipment works end to end on staging, a test-mode EasyPost label comes back, and the open questions in section 9 are answered.

### Phase 1: Shipment capture (about 3 to 5 days)

- **Create Shipment** button on Delivery Note with the defaults above.
- Parcel Template quick-pick, with a note on units (in, lb) on the form.
- Validation: at least one parcel, positive weight and dimensions before labels.
- Shipping lead permissions (who can create and submit Shipments, who can buy and void labels).
- **Exit:** staff can pack and record boxes in under two minutes for a typical order.

### Phase 2: Label automation with EasyPost (about 5 to 8 days)

- Custom fields from section 5.
- **Create Labels** and **Void Label** buttons, with the n8n workflow (HTTP Request nodes to EasyPost), credentials and error handling: address verification failures, rate errors, API outages, and a duplicate-click guard using `ill_label_status`.
- Write-back of tracking numbers, label PDF, EasyPost shipment ID and cost.
- Mirror hook to Delivery Note.
- Surcharge flagging: show EasyPost's returned rate and fees to staff before they confirm the purchase, and flag length, weight and girth thresholds from the FedEx agreement.
- **Exit:** a multi-box test shipment gets one master number and per-box numbers, the label prints, and a void works.

### Phase 3: Tracking and portal (about 3 to 5 days)

- Rewrite `portal/shipment_tracking.py` to return a **list** of `{carrier, number, url}` built from linked Shipments, with the legacy fallback kept for old Delivery Notes.
- Update the portal order page, shipment email context, the Delivery Note and Packing List print formats, and the command center gateway to loop over the list.
- n8n webhook handler for EasyPost tracker events updates `tracking_status`. Add a delivered email and an exception alert to the shipping lead.
- Update `tests/portal_unit/test_shipment_tracking.py` for multi-package and legacy cases.
- **Exit:** a two-shipment order shows both tracking links to the dealer, and a delivered status shows without manual entry.

### Phase 4: Inbound DHL (about 3 to 5 days)

- Build the DHL tracking URL from the waybill. (`forwarder` is already a link to Supplier.)
- Tracker-based update of ATA, status and delivered date on open Inbound Shipments.
- Purchasing board late-shipment flag.
- Incoterm required on POs, and a landed cost checklist on the Inbound Shipment.
- **Exit:** an open DHL import updates itself and shows lateness on the board.

### Phase 5: Freight estimates at quote time (optional, about 5 to 8 days)

- Item dimension fields and configurator computed weight and length on Sales Order lines.
- Freight estimate line on quotes using a zone and weight table, or an EasyPost rate call.
- **Exit:** quote freight is within an agreed tolerance of the actual label cost on a sample of recent orders.

*Estimates are rough and assume one developer familiar with the codebase. They exclude carrier account setup and user training.*

## 8. Multiple shipments per Delivery Note

- Same ship event, several boxes: one Shipment, many parcel rows, bought as one multi-piece EasyPost shipment.
- Different days or carriers: separate Delivery Notes, each with its own Shipment.
- The tracking helper reads **all Shipments linked to the Delivery Note**, so the portal is correct even if an exception puts two on one note.
- If staging shows that one Delivery Note cannot sit on two Shipments, no change is needed because the rules above already avoid it.

## 9. Open questions and risks

**Still open**

1. Invoicing trigger (working assumption above).
2. The shipping lead's answers on box sizes, pickup schedule, oversize policy and label printer (see the Shipping Lead Summary).
3. Whether EasyPost's multi-piece FedEx Ground support and tracker coverage of our DHL service type match what we need (Phase 0).

**Risks**

| Risk | Mitigation |
| --- | --- |
| Native Shipment required fields add friction | Defaults in Phase 1 |
| Staff enter wrong dimensions or weight | Parcel Templates, validation, rate shown before purchase |
| Surcharges on long fixtures | Rate and fee display before purchase, surcharge flag, quote-time estimate (Phase 5) |
| Pounds sent to EasyPost where ounces are expected | Conversion in one place in the n8n workflow, covered by a test shipment |
| Duplicate label purchase from a double click | `ill_label_status` guard and a confirmation step |
| EasyPost outage or bad address | Error status on Shipment, manual label fallback, keep the existing manual tracking entry |
| Portal regression when tracking becomes a list | Keep the legacy fallback, update tests first |
| Landed cost misstated on partly sold imports | Document that the LCV only revalues stock on hand |

**Not yet verified:** how this ERPNext version validates one Delivery Note on multiple Shipments, whether submit requires parcels, and the exact FedEx surcharge thresholds in our rate agreement. All three are covered by the Phase 0 spike.

## 10. Acceptance and testing

- Unit tests for the tracking helper: no Shipment, one Shipment, several Shipments, legacy fields only.
- Test-mode EasyPost walkthrough on staging with the shipping lead: single box, multi-box, split order, voided label, label error, delivered status.
- Dealer portal and email checked with a multi-tracking order.
- Inbound: a DHL waybill that updates through delivery, and a landed cost voucher that posts.
- Run the Frappe test suite, `ruff check .` and `ruff format .` before release.

## 11. Rollout

1. Build and test on staging with EasyPost test mode.
2. Pilot with one shipping station for a week on production keys, with manual tracking entry still available.
3. Compare label cost and estimate vs actual, and fix the parcel templates.
4. Cut over fully and remove the manual step.

## 12. Build status (2026-11-22)

**Built in the repo (Phases 1 to 3):**

- ilL-Shipping-Settings, the Shipment and Shipment Parcel custom fields, unit labels (in, lb) on Shipment Parcel and Parcel Template, and the shipping integration user (patch `add_shipping_label_fields`).
- **Create Shipment** on Delivery Note (draft or submitted) with every default in section 6, including the delivery contact the native Shipment requires and a suggested parcel from Item weights. Opens the existing Shipment when one already lists the note.
- Shipment hooks: rows with Count above 1 become one row per box (each box needs its own label and tracking number), surcharge flags, submit blocked without usable parcels or over the hard limits, cancel blocked while labels are bought.
- **Create Labels** (rate, then confirm, then buy), **Void Label** and **Print Labels**, gated on Submit permission for Shipment. Write-back of numbers, labels (merged into one attached PDF), cost and EasyPost id, and the mirror to the Delivery Note. Double clicks are stopped by a row lock and by reusing the EasyPost order from the rate step.
- Signed tracker endpoint: per-box status, Shipment `tracking_status`, Completed on delivery, exception email to the shipping lead, and an optional delivered email to the dealer.
- `shipment_tracking.py` returns every package. The portal order page, the shipment and delivered emails, the email context and both print formats show all of them.
- n8n workflows `n8n_workflows/shipping_easypost_labels.json` and `shipping_easypost_tracker.json` (not yet imported or run against EasyPost).
- Unit tests: `test_shipment_tracking.py`, `test_shipping.py`, `test_shipping_rules.py`.

**Still to do:** Phase 0 (staging spike, EasyPost and FedEx account, test keys), importing and testing the n8n workflows against EasyPost test mode, confirming the surcharge thresholds against our FedEx agreement, Phases 4 and 5.

**Known gaps to decide on:**

- Buying labels after the Delivery Note is submitted means the shipment email has already gone without tracking. The flow assumes labels first, then submit.
- A void with many boxes runs the refunds one at a time in n8n and could pass ERPNext's 60 second wait. The refunds still go through, and a second Void Label skips boxes already refunded.
- Native Shipment refuses submit when the value of goods is 0 (for example a no-charge replacement). Staff must enter a value by hand.
