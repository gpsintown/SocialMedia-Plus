# Optional LinkedIn developer setup

Checked against official documentation on 14 September 2026. Portal labels and access programs can change; the products and granted scopes shown for your own app are authoritative.

## Use the browser workflow first

For the current LinkedIn workflow, your copilot uses supported browser tools and your signed-in account. It can read discussions, comment, reply and submit authorized content through the visible interface. Follow [initial setup](getting-started.md) to verify that access; you can skip developer apps for browser work.

This guide prepares optional developer configuration for future API adapters. The dashboard saves two sets of app settings to your private `.env.local`. It does not complete OAuth, obtain tokens or publish through the LinkedIn API. The reserved callback addresses below are examples, not working routes.

The two-app arrangement separates identity from publishing. It is a project configuration choice; LinkedIn does not require two apps for every integration. You may complete only the app setup you need. Do not put the same secret into unrelated apps merely to make both dashboard cards appear configured.

| App | Suggested name | Product to request | OAuth scopes | Purpose |
| --- | --- | --- | --- | --- |
| Identity | `Social Media Plus Identity` | **Sign In with LinkedIn using OpenID Connect** | `openid profile`; add `email` only if needed | The consenting member's identity information |
| Publishing | `Social Media Plus Publisher` | **Share on LinkedIn** | `w_member_social` | Member publishing and supported social writes |

LinkedIn documents OIDC and Share as self-service products. Their scopes require member consent; an app client secret alone does not authorize account access. [API access](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access)

## 1. Prepare your own app information

Have your LinkedIn account, an appropriate LinkedIn Page when the portal requires one, your own app logo, and a real privacy-policy URL ready. The Page represents the publisher of the app. Do not use this repository's maintainer as the publisher or copy somebody else's company identity. LinkedIn's app-creation form collects the app name, Page, privacy policy, logo, and agreement to its terms. [Create an app](https://www.linkedin.com/help/linkedin/answer/a1667239)

## 2. Create the identity app

1. Open the [LinkedIn Developer Portal](https://www.linkedin.com/developers/apps) and sign in yourself.
2. Choose **Create app**. Fill the app information using your details and a distinct name such as `Social Media Plus Identity`.
3. Complete any Page verification requested in the portal. If you need a Page administrator to verify the app, use the portal's verification flow.
4. Open the app's **Products** tab. Request **Sign In with LinkedIn using OpenID Connect** and complete the displayed enrollment steps.
5. After access is granted, inspect **Auth → OAuth 2.0 scopes**. The future authorization flow should request `openid profile`, adding `email` only when it actually uses email. OIDC returns information for the consenting member, not arbitrary LinkedIn profiles. It is not an identity-verification service. [OIDC setup and scopes](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2)
6. In **Auth**, record the app's Client ID and Client Secret in your local settings. Keep the secret out of chat, screenshots, issues, and Git history.
7. For a future OAuth adapter, reserve `http://127.0.0.1:4010/auth/linkedin/identity/callback` as the redirect URI if accepted by the portal. **Do not start an authorization flow against it in this release.**

## 3. Create the publishing app

1. Return to **My apps → Create app** and repeat the creation process with `Social Media Plus Publisher`.
2. Open **Products** and request **Share on LinkedIn**.
3. Once granted, check that **Auth → OAuth 2.0 scopes** includes `w_member_social`. This is the documented permission used for publishing on the consenting member's behalf. [Share on LinkedIn](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/share-on-linkedin)
4. Record this app's own Client ID and Client Secret in the publishing section of local settings.
5. Reserve `http://127.0.0.1:4010/auth/linkedin/publish/callback` for a future adapter if the portal accepts it. It is not a working callback in this release.
6. If a future publishing adapter also needs OIDC identity, request the OIDC product **on this publishing app** and consent to the required scopes there. A token issued for the identity app is not a publishing token for the other app. Do not assume member identifiers from separate OIDC clients are interchangeable.

An implemented OAuth flow must send exactly the registered redirect URI, validate its anti-forgery state, and use the matching app credentials when exchanging the code. Changing `127.0.0.1` to `localhost`, changing the port, or changing the path produces a different URI. If the portal requires HTTPS for your app, use an adapter with an actual HTTPS callback; do not register a pretend working endpoint. [Authorization code flow](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow)

## 4. Save the settings in the dashboard

1. Start the local application using your [Codex](codex-setup.md) or [Claude](claude-setup.md) setup guide.
2. Open [the local dashboard](http://127.0.0.1:4010), select **LinkedIn**, then open its app settings.
3. Enter each app's Client ID, Client Secret, and redirect URI in the matching identity or publishing section, then save.
4. Confirm the presence status changes. **Configured means fields were saved; it does not mean authenticated.** Secret fields are not read back into the page. Leaving a field blank keeps its saved value; use the explicit clear control to remove an app's saved settings.

The corresponding keys are:

```dotenv
LINKEDIN_IDENTITY_CLIENT_ID=""
LINKEDIN_IDENTITY_CLIENT_SECRET=""
LINKEDIN_IDENTITY_REDIRECT_URI=http://127.0.0.1:4010/auth/linkedin/identity/callback
LINKEDIN_PUBLISH_CLIENT_ID=""
LINKEDIN_PUBLISH_CLIENT_SECRET=""
LINKEDIN_PUBLISH_REDIRECT_URI=http://127.0.0.1:4010/auth/linkedin/publish/callback
```

The repository includes `.env.example`; real values belong in ignored `.env.local`. On POSIX systems, manual edits must preserve owner-only permissions (`chmod 600 .env.local`). No access token is requested or generated by the settings form.

## Optional: approved analytics and community APIs

The core workspace does not depend on these products. Adding basic OIDC or Share access does not unlock analytics, a home feed, connection/follower rosters, recruiter tools, private messages, or InMail.

**Community Management API** is a vetted program with Development and Standard tiers. Its current guidance says to request Development access with a new app that has no other API products. Do not add random products first to a proposed Community Management app. A separate application may therefore be needed beyond the two basic app slots above. `r_member_social` is a closed permission, with access requests currently unavailable. [Program overview and access FAQ](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/community-management-overview?view=li-lms-2026-07)

For an eligible integration:

1. Read the permitted use cases and create the appropriate new app.
2. Request Community Management Development access under **Products** and submit the access form.
3. Supply genuine organization details, a verified business email, website, privacy policy, and Page verification. Approval is reviewed, not guaranteed.
4. Build and test the approved use case. For Standard access, follow the portal's separate review and demonstration requirements. Do not present this settings-only release as a completed API integration. [App review requirements](https://learn.microsoft.com/en-us/linkedin/marketing/community-management-app-review?view=li-lms-2026-07)

| Optional scope | Documented use | Access condition |
| --- | --- | --- |
| `r_member_postAnalytics` | Analytics for the consenting member's posts | Approved Community Management access; supported API version |
| `r_member_profileAnalytics` | Member profile analytics | Approved Community Management access; supported API version |
| `r_organization_social` / `w_organization_social` | Relevant organization content reads/writes | Approved product access and qualifying Page role |
| `r_organization_social_feed` / `w_organization_social_feed` | Relevant organization social actions | Approved product access and qualifying Page role |

These are examples to match an implemented use case, not a list to request wholesale. Confirm the actual scopes granted in **Auth** and each endpoint's requirements. A metric count does not grant access to a roster of the people behind it. [Marketing permissions and tiers](https://learn.microsoft.com/en-us/linkedin/marketing/increasing-access?view=li-lms-2026-07)

## Troubleshooting

| Symptom | Check |
| --- | --- |
| A product or scope is missing | Product enrollment may be pending, unavailable, or require review. Typing a scope into a file cannot grant it. |
| Callback returns an error | This release has no OAuth callback handler. Implement and validate an adapter before attempting OAuth. |
| Both app cards say configured | This only describes local field presence. There are still no OAuth tokens or verified API capabilities. |
| No analytics or network history | Import your own exports or use a supported observed browser workflow. Missing observations stay unavailable. |
| Browser work cannot continue | Open the authorized Chrome session and resolve account login or challenges yourself. Never extract cookies or use hidden APIs. |
