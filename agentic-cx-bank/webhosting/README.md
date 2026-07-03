# webhosting — static website hosting construct

CDK **construct** (not a standalone app) that deploys the Vite-built
website to a private S3 bucket served through CloudFront with Origin
Access Control (OAC). It is instantiated by the main stack
(`agentic_cx_bank/website_stack.py`) so the website ships with the rest
of the infrastructure-as-code.

## Layout

```
webhosting/
  __init__.py
  webhosting_construct.py   # Webhosting(Construct): S3 (private) + CloudFront (OAC) + BucketDeployment
```

## What it creates

- A private S3 bucket (`BLOCK_ALL` public access).
- A CloudFront distribution with `S3BucketOrigin.with_origin_access_control`
  (OAC), `REDIRECT_TO_HTTPS`, and SPA-style 403/404 → `/index.html` mapping.
- A `BucketDeployment` that uploads `website/dist` and invalidates the
  distribution cache on deploy.

## Configuration

All values live in the top-level `config.py` (the flat project config),
prefixed `WEBSITE_*`:

- `BUILD_WEBSITE` — gate the construct on/off.
- `WEBSITE_ASSETS_PATH` — the Vite build output (`website/dist`), relative
  to the CDK project root.
- `WEBSITE_PRICE_CLASS`, `WEBSITE_HTTP_VERSION`,
  `WEBSITE_VIEWER_PROTOCOL_POLICY`, `WEBSITE_ERROR_RESPONSES`,
  `WEBSITE_DEFAULT_ROOT_OBJECT`, `WEBSITE_INVALIDATION_PATHS`,
  `WEBSITE_DESTINATION_KEY_PREFIX`.

The site is **static** — the Amazon Connect widget configuration is baked
into `website/index.html`, so there are no runtime `VITE_*` env vars to
validate. The construct's only synth-time check is that `website/dist`
exists (so it never deploys an empty bucket).

## Deploy

Build the site first, then deploy the main stack:

```bash
cd website && npm run build && cd ..
cdk deploy --profile <your-profile>
```

Outputs: `WebsiteDistributionDomainName`, `WebsiteDistributionId`,
`WebsiteBucketName`.

To deploy the backend without the website (e.g. `website/dist` not built),
set `BUILD_WEBSITE = False` in `config.py`.
