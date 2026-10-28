# Local recipient and bounded capture preparation

`scripts/macos_prepare_recipient.swift` is a macOS-only administrative helper for an explicitly requested new local recipient. It reserves a new private directory and never overwrites an existing one. It uses macOS secure randomness, creates one dedicated non-synchronizing Keychain item, generates an encrypted RSA-3072 private key and a self-signed public recipient certificate, and checks a CMS AES-256-GCM/RSA-OAEP-SHA-256 roundtrip using a dummy marker only.

The random unlock secret is passed to OpenSSL through stdin, not a shell argument or passphrase file. It is stored only in the dedicated Keychain item. The private key is written only in encrypted form, with private file permissions. The public certificate pin and Keychain lookup references are saved in private recipient metadata. The helper prints status booleans only. Neither a real recipient's files nor Keychain values belong in Git, chat or logs.

Compile with the macOS SDK and a task-owned module cache, then run the helper only with explicit recipient-creation authorization and a new directory beneath ignored private evidence storage. Linux CI does not run this helper or touch Keychain. Local compilation and a real local dummy-message roundtrip verify the native setup path. Python archive tests continue to use entirely separate ephemeral synthetic recipients.

This certificate is an encryption recipient, not a claim of signed capture authorship or a public certification authority's identity assurance. Preserve both the encrypted private key and its Keychain item: losing either can make archives unreadable. The helper does not export a recovery secret, create a cloud secret/KMS key, configure AWS authentication or start a capture. Production decryption remains a caller-owned boundary.

## Request bounds

Both Python collectors now accept independent max-items and max-pages controls. Each paginated operation allows at most 1,000 items and 20 pages, with lower values available for the first authorized inspection. A page continuation at the page cap produces an explicit incomplete record before another SDK page is requested. Item counts alone cannot bound empty continuation pages. Retry attempts remain separately limited by SDK configuration.

A first development inspection should use one page and 50 items per paginated operation, one reviewed bucket, a new encrypted output directory for each collector, and a fixed closed history interval. Its purpose is software/format validation only. A current state snapshot cannot be paired with older history to claim temporal compliance, ML performance or a valid 30-minute experiment. Retrospective receipts and lack of independent delivery verification remain explicit blockers.

The exact capture interval, recipient pin, selected bucket, source hashes, private output paths and approved commands must be retained in a private review before execution. No live collection is authorized by key preparation, these request limits or merging this source change. AWS monitoring remains paused until a separate reviewed activation plan is approved.
