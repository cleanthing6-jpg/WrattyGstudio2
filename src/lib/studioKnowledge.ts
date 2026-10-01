// Facts only. Rules live in the SYSTEM prompt in /api/support/route.ts.
export const STUDIO_KNOWLEDGE = `
## Who we are
WraGstudio (operated by Wrattygstudio) is an AI mixing and mastering studio
built for African sounds. We mix and master songs. We do NOT generate beats
and we do NOT design album covers.

## Services
1. Mix & Master - /studio (the main service)
   Upload stems (lead vocal, backing vocal, ad-lib, beat/instrumental) or a
   rough phone recording. The engine returns a finished, release-ready mix
   and master.
   - Preview is FREE: 30 seconds, watermarked.
   - Unlocking the FULL mix spends 1 MIX credit.
   - Beat-Lock option: the beat passes through untouched, only the vocals go
     to the engine. Use it when the beat is already perfect.
2. Master only - /master
   For an already-finished stereo mix. Upload one file; it runs the mastering
   chain (EQ polish, stereo width, brickwall limiter).
   - Preview is FREE: 30 seconds.
   - The FULL master spends 1 MASTER credit. A mix pack does NOT cover it.
3. Splitter (inside /studio, "Splitter" mode)
   Splits a full song into Vocals + Instrumental so it can be mixed.
   Backups and ad-libs stay combined inside the vocal stem.
   Free accounts: 1 split per day. Paid accounts: 5 per day. Costs no credits.
4. Beat-Locked Mix - /beatlock
   Browser tool. Beat untouched, vocal only. Instant, no credits.
5. Tune - /tune
   Browser tool. Reads the key from the beat and tunes the vocal to it.
   No credits.

## Mix controls
- Style: Afrobeats (recommended), Hip-Hop/Rap, Reggae/Dancehall, Pop,
  Electronic/Amapiano, Acoustic, Rock/Indie, Other.
- Master loudness: LOW (most dynamic), MEDIUM (streaming standard),
  HIGH (loudest).
- Vocal space: Studio, Room, Hall, Cathedral, Plate Shine.

## Prices - one-off, credits NEVER expire
All prices are in Naira (NGN) for Nigeria. International customers pay USD.

Mix & Master packs (1 mix + master each):
  Single    N7,500   - 1 finished mix + master      (USD $12)
  EP Pack   N25,000  - 5 finished mixes + masters   (USD $45)
  Album     N45,000  - 10 finished mixes + masters  (USD $80)

Mastering-only packs (master an existing stereo mix):
  Master Single  N5,000   - 1 stereo mix mastered   (USD $8)
  Master EP      N17,500  - 5 stereo mixes mastered (USD $30)
  Master Album   N31,500  - 10 stereo mixes mastered (USD $52)

Free plan: 30-second preview only, no full download.

Credits are ADDITIVE. Buying again adds to the balance; it never resets and
never wipes the other type. Mix credits and master credits are separate.

## Rendering and credits
- A credit is spent when a full render STARTS.
- If a render FAILS the credit is refunded automatically. Tell the user to
  refresh the dashboard and it will be back.
- Previews never spend credits.
- Renders take a few minutes. Tell users NOT to resubmit; it queues and
  starts automatically. One job runs at a time.
- Free accounts: 30-second renders, limited per day.

## Payments
Handled by Paystack (card, bank transfer, USSD). After payment the user
returns to the dashboard and credits are granted automatically.
If a user paid but sees no credits: ask them to refresh, then check the
Dashboard. If it is still missing, escalate - do not promise a refund.

## Uploading
- WAV uploads skip conversion and are fastest. MP3 and other formats convert
  in the browser first, which is slower on phones.
- Upload stems separately, one per file, for the best result.
- Only use the Splitter if the user has no stems.

## Refunds
YES - full refund if a payment succeeded but the plan never activated, or a
render failed and the user was actually charged. Must be reported within 7 days.
NO - change of mind after using render credits, or dissatisfaction with a mix
they could have previewed free first. Unused credits stay on the account.
HOW - email wrattyg@gmail.com with the Paystack reference. Money returns to
the original payment method.

## Rights and data
Users keep all rights to their renders. We store email, uploads and usage
counters; uploads are deleted on a rolling schedule; we never sell data.
We never see or store card details.

## Never promise
Perfect vocal removal, a specific artist's sound, guaranteed commercial or
copyright clearance, uninterrupted uptime, unlimited free retries, instant
human support, or a refund you are not authorised to give.

## Contact
Refunds and account issues: email wrattyg@gmail.com
Everything else, or a requested human: https://wa.me/2347074216877
`;
