# Database certificate trust

`supabase-prod-ca-2021.crt` is a public CA certificate downloaded from the
project's Database Settings certificate link on October 9, 2026:
https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

Downloaded SHA-256:
`700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7`.
This is public trust material, not a client credential or private key.

Both remote application pools require this trust chain and a matching hostname.
For a Supabase CA rotation or a different database provider, set
`DATABASE_SSL_ROOT_CERT` to a reviewed CA file. Invalid or missing configured
files hold connections. Never fix a certificate error by disabling verification.
Do not assume the bundled CA covers all providers or future Supabase certificates.
