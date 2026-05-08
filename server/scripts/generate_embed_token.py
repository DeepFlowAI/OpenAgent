"""
Generate an Embed Token for a channel — complete workflow.

Steps:
  1. Look up channel by routing token
  2. Generate secret_key if not present (via API or direct DB)
  3. Sign an embed token with customer context
  4. Print the ready-to-use chat URL

Usage:
  # Basic — only channel token required, uses defaults for everything else
  python generate_embed_token.py --channel-token byp5C94eEyB21c6K3PYxZg

  # Full — specify all customer context fields
  python generate_embed_token.py \
    --channel-token byp5C94eEyB21c6K3PYxZg \
    --external-user-id crm-user-42 \
    --display-name "张三" \
    --email zhangsan@example.com \
    --phone "+8613800138000" \
    --avatar-url "https://api.dicebear.com/7.x/avataaars/svg?seed=demo" \
    --title "客服咨询" \
    --metadata '{"vip_level":"gold"}' \
    --ttl 3600

  # Use --base-url to point at a different environment
  python generate_embed_token.py \
    --channel-token abc123 \
    --base-url https://your-deployment.example.com

Environment:
  Run from server/ with virtualenv activated:
    cd server && source venv/bin/activate && python scripts/generate_embed_token.py ...
"""

import argparse
import json
import sys
import os

# Allow importing app modules when running from server/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main():
    parser = argparse.ArgumentParser(
        description="Generate an Embed Token for a Web SDK channel"
    )
    parser.add_argument(
        "--channel-token", required=True,
        help="Channel routing token (the string in the URL path /chat/{token})",
    )
    parser.add_argument("--external-user-id", default=None, help="Business user ID")
    parser.add_argument("--display-name", default=None, help="Display name in chat")
    parser.add_argument("--email", default=None, help="User email")
    parser.add_argument("--phone", default=None, help="User phone (E.164)")
    parser.add_argument("--avatar-url", default=None, help="Avatar HTTPS URL")
    parser.add_argument("--title", default=None, help="Conversation title")
    parser.add_argument(
        "--metadata", default=None,
        help='Custom metadata as JSON string, e.g. \'{"key":"value"}\'',
    )
    parser.add_argument(
        "--source", default="embed", choices=["embed", "chat"],
        help="Source tag (default: embed)",
    )
    parser.add_argument(
        "--ttl", type=int, default=86400,
        help="Token TTL in seconds (default: 86400 = 24h, max: 604800 = 7d)",
    )
    parser.add_argument(
        "--base-url", default="http://localhost:3000",
        help="Frontend base URL for the generated link (default: http://localhost:3000)",
    )
    args = parser.parse_args()

    # Parse metadata JSON
    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError:
            print(f"ERROR: --metadata is not valid JSON: {args.metadata}")
            sys.exit(1)

    import asyncio
    asyncio.run(_generate(args, metadata))


async def _generate(args, metadata):
    from app.db.session import AsyncSessionLocal
    from app.repositories.channel_repository import ChannelRepository
    from app.services.channel_service import ChannelService
    from app.core.embed_token import sign_embed_token

    async with AsyncSessionLocal() as db:
        # 1. Look up channel
        channel = await ChannelRepository.get_by_token(db, args.channel_token)
        if not channel:
            print(f"ERROR: Channel with token '{args.channel_token}' not found")
            sys.exit(1)

        print(f"Channel found: id={channel.id}, name={channel.name}, "
              f"agent_id={channel.agent_id}")

        # 2. Ensure secret_key exists
        if not channel.secret_key:
            print("Channel has no secret_key — generating one...")
            channel = await ChannelService.generate_secret_key(db, channel.id)
            print(f"Secret key generated: {channel.secret_key}")
        else:
            print(f"Secret key exists: {channel.secret_key[:12]}...")

        # 3. Sign embed token
        token = sign_embed_token(
            channel.secret_key,
            channel_id=channel.id,
            tenant_id=channel.tenant_id,
            external_user_id=args.external_user_id,
            display_name=args.display_name,
            email=args.email,
            phone=args.phone,
            avatar_url=args.avatar_url,
            source=args.source,
            title=args.title,
            metadata=metadata,
            ttl=args.ttl,
        )

        # 4. Print results
        print()
        print("=" * 60)
        print("  Embed Token Generated Successfully")
        print("=" * 60)
        print()
        print(f"Token (JWT):  {token[:50]}...")
        print(f"Expires in:   {args.ttl}s ({args.ttl // 3600}h {(args.ttl % 3600) // 60}m)")
        print()

        # Customer context summary
        ctx_fields = {
            "external_user_id": args.external_user_id,
            "display_name": args.display_name,
            "email": args.email,
            "phone": args.phone,
            "avatar_url": args.avatar_url,
            "source": args.source,
            "title": args.title,
            "metadata": metadata,
        }
        print("Customer Context:")
        for k, v in ctx_fields.items():
            if v is not None:
                print(f"  {k}: {v}")
        print()

        base = args.base_url.rstrip("/")
        ct = args.channel_token

        print("URLs:")
        print()
        print(f"  URL mode (full page):")
        print(f"  {base}/chat/{ct}?token={token}")
        print()
        print(f"  Embed mode (iframe):")
        print(f"  {base}/chat/{ct}?embed=1&token={token}")
        print()


if __name__ == "__main__":
    main()
