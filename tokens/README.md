# Token Materials

> ⚠️ **Security**: Do not commit private keys or production secrets here.

## Purpose

This directory holds cryptographic materials used to:
- **Sign agent cards** (private JWK/PEM)
- **Verify signatures** (public JWKS)

---

## What's Protected

The repository `.gitignore` excludes everything under `tokens/` except this README:

```
tokens/*              # except tokens/README.md
jwks.json
jwk_*.json
*.pem, *.key, *.crt
```

---

## Quick Start (Optional Local Key)

Generate a dev keypair and JWKS:

```bash
cd tokens

python3 <<'EOF'
from authlib.jose.rfc7517.jwk import JsonWebKey
import json

key = JsonWebKey.generate_key('RSA', 2048, options={'kid': 'local-dev-key', 'use': 'sig', 'alg': 'RS256'}, is_private=True)
open('jwk_private.json','w').write(json.dumps(key.as_dict(is_private=True), indent=2))
open('jwks.json','w').write(json.dumps({'keys':[key.as_dict(is_private=False)]}, indent=2))
print('✅ Generated jwk_private.json and jwks.json')
EOF
```

> **Note**: You don't have to create keys locally. During OpenShift deployment, the script auto-generates a signing key if none is provided and publishes the public key to the central JWKS.

---

## OpenShift

### Central JWKS Server

Stand up empty or seeded JWKS:

```bash
# Create empty JWKS (recommended)
./mock_agent/setup_central_jwks.sh

# OR seed from existing file
./mock_agent/setup_central_jwks.sh /path/to/jwks.json

# OR merge keys
./mock_agent/setup_central_jwks.sh /path/to/jwks.json --merge
```

### Deploy an Agent

The deploy script handles keys automatically:

```bash
cd mock_agent

# Optional: use a pre-generated key
export A2A_SIGNING_JWK_PATH="../tokens/jwk_private.json"

# Deploy with central JWKS
./deploy.sh <AGENT_NAME> --jwks-url https://<route>/.well-known/jwks.json
```

The deploy script will:
1. Create a signing secret (or use your provided key)
2. Derive the public key
3. Merge it into the central JWKS

---

## Environment Variables

### Agent (Signing)

- `A2A_SIGNING_JWK_JSON` - Inline private JWK
- `A2A_SIGNING_JWK_PATH` - Path to JWK/PEM file
- `A2A_PUBLISH_JWKS` - Publish JWKS endpoint (`true`/`false`)

### Verifier (MCP Bridge)

- `A2A_TRUSTED_JWKS_JSON` - Inline public JWKS
- `A2A_TRUSTED_JWKS_PATH` - Path to JWKS file
- `A2A_TRUSTED_JWKS_URL` - URL to fetch JWKS

---

## Production Guidance

- ✅ Use a secret manager or KMS/HSM
- ✅ Inject secrets at deploy time (Kubernetes Secrets, CI secrets)
- ✅ Rotate keys periodically
- ❌ Don't store production keys in git
