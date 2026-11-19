# Your first confirmed definition

About 40 minutes, two Builders (call them Builder A and Builder B), the service running ([QUICKSTART.md](QUICKSTART.md)), and the files in [sample/](sample/). The data is made up: 150 orders, 40 customers, status codes 0 to 5. The sample has one deliberate trap: cancelled (4) and refunded (5) orders still carry an amount, so a plain "total of amount" counts them as revenue.

The correct numbers are in `sample/expected_numbers.txt`: all orders sum to 162,960 (wrong as revenue), paid, shipped and delivered orders (codes 1, 2, 3) sum to **119,810** (right). Regenerate the files any time with `python3 docs/pilot/sample/make_sample.py` (fixed seed, same output).

What each file is:

| File | Upload? | What |
|---|---|---|
| `customers.csv` | yes | customer_id, name, city, tier |
| `orders.csv` | yes | order_id, customer_id, order_date, amount, status_code |
| `order_status_notes.csv` | optional | The ops team's notes on what each code means. Read it while writing meanings |
| `orders_update.csv` | step 8 | A later extract: 6 changed rows, 4 new rows, one with a new code 6 |

## 1. Upload (Builder A)

Open **Data > Datasets**, click **Upload**, choose `orders.csv` and `customers.csv`, and click **Upload**. Two datasets appear (150 and 40 rows). Open `orders`: the **Preview** tab shows the rows and **Versions** shows version 1.

## 2. Create the object type (Builder A)

Open **Business objects > Object types > New object type**.

- Name: `Order`. Dataset: `orders`.
- Properties: tick all columns. Set `order_id` as the **Key**, then click **Check key**: it reports all 150 rows checked, no duplicates, no blanks.
- Open **Advanced settings: property types, code columns** and tick **Code column** for `status_code`. A code column keeps 0 to 5 as numbers and asks a person to write what each value means.
- Click **Create**.

(With a model key you can try **Suggest from datasets** instead; whatever it proposes is only a draft and goes through the same steps below.)

## 3. Write what the codes mean (Builder A)

Open the `Order` type, tab **Properties**, and find `status_code` ("Meanings not written"). Click **Edit meanings**. The table lists each value with its row count. Write the meaning of each value from `order_status_notes.csv`:

| Value | Meaning |
|---|---|
| 0 | New |
| 1 | Paid |
| 2 | Shipped |
| 3 | Delivered |
| 4 | Cancelled |
| 5 | Refunded |

Click **Propose these meanings**. The service checks them against the data (every value present in the data has a meaning, none is left over). Meanings count only after another builder confirms them.

## 4. Confirm (Builder B)

Sign in as Builder B in another browser. Open **Business objects > Review queue**: the `Order` object type and the `status_code` meanings are waiting, each marked as needing another builder. Open each, read the checks and what the data shows (the rows per value), and click **Confirm this object type** and **Confirm these meanings**. Builder A cannot confirm their own proposal; that is the point. The confirmation keeps the data version and who confirmed.

Do the same for `Customer` (key `customer_id`; `tier` can be a code column: A, B, C) if you want to ask about customers.

## 5. The wrong number (any user)

Open **Assistant** and ask: *What is the total amount of all orders?* The answer is 162,960, and it is a correct sum of the column. It is also not revenue. This is the moment to notice: nothing in the data says refunds are not revenue; only a person who knows the business does. Write the question and the answer in `QUESTION_LOG.csv` with the verdict you judge it (a plain sum is "right" as arithmetic, "wrong" as the revenue you meant; note which in the notes).

## 6. Define "valid" once (Builder A, then B confirms)

On the `Order` type open the **Views** tab and click the button for a new view (**New view**). Name it `Valid orders`, choose **Keep only the rows that match these conditions**, and set conditions on `status_code` with **is not**: New, Cancelled and Refunded (add each further one with **Add another condition**; conditions use the meanings you confirmed, which is why step 4 comes first). "Valid" here means Paid, Shipped or Delivered; your own team may define it differently, and writing that down is the point. The view shows "Now keeps N / 150 rows". Save; Builder B confirms it from the Review queue with **Confirm this view**.

Ask again: *What is the total amount of valid orders?* The answer must be **119,810**. The answer card shows which definitions it used ("Per confirmed definitions: ...") and who confirmed them. Log it: verdict `right`.

## 7. See it refuse

Ask something that uses a definition nobody has confirmed. For example, as Builder A create a second type `Customer` and do not confirm it, then ask: *How many customers are in Shenzhen?* The Assistant answers "No answer" with the reason (the definitions this question uses are not usable yet), and does not guess from the raw table. Log it: verdict `refused`, and `refusal_reason_ok` = `y` if the reason is true.

## 8. Change the data and watch the definitions go back

Open the `orders` dataset, click **Upload new version**, choose `orders_update.csv`, choose **Update by key** with the key `order_id`. The file changes 6 amounts, adds 4 orders, and one has a status code (6) nobody has written a meaning for. The upload dialog warns how many items it sends back to **Needs review**. After uploading, open the **Review queue**: the `Order` type, the `status_code` meanings and the `Valid orders` view are back as "Needs review", with the cause (the data changed). On `status_code`, code 6 has no meaning yet.

Ask the valid-orders question again: it is **not answered** until the meanings are re-confirmed. Write the meaning of 6 (say "On hold"), propose, have Builder B confirm, and the question is answered again, with the new data version in the answer's basis. This refusal is the product doing its job; log it as `refused` with `refusal_reason_ok` = `y`.

## What to take away

You should now have: one confirmed type, one confirmed set of code meanings, one confirmed view, one wrong number caught, one refusal after a data change. If any step surprised or blocked you, write it in `QUESTION_LOG.csv` notes and use **Send feedback** in the avatar menu. Then bring a real table of your own and repeat steps 1 to 6 with it.

*Not run end to end with a live model while writing this: Assistant wording and exact numbers of the status line vary with the model, so treat the figures in `expected_numbers.txt` as the check, not the sentence the Assistant writes.*
