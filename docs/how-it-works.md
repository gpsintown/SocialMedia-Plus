# How Social Media Plus works

Social Media Plus gives your desktop AI copilot a repeatable way to manage social media through your signed-in browser. You supply your profile, objectives and audience. The project supplies workflows, a dashboard and local records. Codex or Claude reads those instructions, uses its available browser tools and saves the results.

LinkedIn is the first supported platform. Instagram, YouTube and other integrations are under development and coming soon. This guide covers the LinkedIn workflows available at launch.

## Find people and join conversations

Use `SMP DISCOVER 30` to look for relevant new people and discussions. Use `SMP NETWORK 30` to focus on your existing connections and observed incoming followers. `SMP ENGAGE 30` mixes useful ongoing conversations with discovery.

The copilot checks your objectives and past interactions, reads the actual discussion, then chooses whether it has something useful to add. It can send contextual comments and replies within the live session you requested. Add `preview` to research and draft without sending anything.

The record includes the target, discussion context, exact response and observed result. An incomplete follower snapshot stays incomplete; a follower count does not identify everyone who follows you.

## Return to replies

Use `SMP REPLIES 30` to focus on conversations already joined. The copilot revisits relevant threads through the browser, reads visible replies and checks whether you already responded. It can continue the conversation within the requested session and record the result for the next visit.

This is follow-up during a session. The package has no continuous LinkedIn notification feed and does not guarantee that every incoming reply has been found. A dashboard listener checks your requests, not LinkedIn notifications.

## Prepare posts, articles and assets

Use `SMP WEEK <Monday date>` to prepare a week of content based on your topics, audience and available evidence. It includes drafts, final supported assets, editorial review and proposed posting times. Assets can include images and carousel PDFs, with editable sources and visual checks when the required tools are available.

Your profile and voice files guide the subject, point of view and wording. The agent should flag a missing source, unsupported claim or unavailable asset tool instead of presenting unfinished work as ready. Use `SMP REWORK <week or content ID>` to revise existing work while retaining its earlier versions.

## Publish and schedule inside LinkedIn

When a batch is finished and you have reviewed it, use `SMP SCHEDULE <week or content ID>`. For immediate publication, give a concrete instruction covering the finished item and destination, following the [publishing workflow](../workflows/publish.md).

The copilot verifies the signed-in account, opens the appropriate LinkedIn composer, enters the exact text and assets, and checks the preview. It uses LinkedIn's own scheduling controls when supported for that format and account. Native articles and feed posts can have different controls; the agent checks the actual editor.

The agent records an item as scheduled only after seeing it in LinkedIn's queue. A time saved in the local plan is not a remote schedule. Once LinkedIn accepts a native schedule, LinkedIn handles delivery; later verification still needs a browser session. Changing a local draft does not change or cancel the remote item.

If the required browser action is unavailable, the agent prepares a manual handoff and reports what remains pending. If a submission may have succeeded but cannot be confirmed, it checks the remote state before trying again.

## Like, repost and share

`SMP ENGAGE+ 30` adds selective likes on items the copilot has read and occasional attributed reposts with a useful perspective. It uses your profile, discussion context and recent history to choose those actions. It does not include private messages or connection invitations.

There is no dedicated LinkedIn Groups publishing workflow in this release. Local relationship groups help organize people; they are not LinkedIn Group memberships or permission to post there.

## Keep track of opportunities

The Opportunities area stores observed hiring openings and the evidence behind a potential match. The optional `SMP RECRUITER+ 30` workflow uses your configured goals, target locations, résumé and contact evidence to assess fresh, close-match openings. Its current selection rules require observed last-24-hour posting evidence and fewer than ten applicants.

Private outreach is disabled until configured and explicitly requested. InMail also requires an opt-in to use existing credits. The workflow does not buy credits, submit job applications or send connection invitations. Read the [recruiter workflow](../workflows/recruiter-plus.md) before enabling it. Ordinary `SMP RECRUITERS 30` stays within public comments and replies.

## Use the dashboard or the chat

A dashboard button saves a request in the local queue. Your desktop agent reads it through the included MCP tools or CLI and performs the workflow. A supported host schedule can check for requests periodically; otherwise type `SMP RUN QUEUE` in the active project chat.

Runs shows request progress. Content, Assets, Engagement, Network and Opportunities show saved work and observations. Insights uses available recorded or imported data. These records help the next session continue without starting from an empty chat.

The desktop host must have access to the same folder and the tools the task needs. See [initial setup](getting-started.md), [the listener guide](listener.md) and [architecture](architecture.md).

## Set the direction

Your niche and audience guide whom the copilot looks for. Your objectives guide which discussions and opportunities matter. Your evidence and writing samples guide what it can say on your behalf. Privacy boundaries determine what stays out of public text.

Start with [personalization](personalization.md), then use the [command guide](../SOCIAL_MEDIA_PLUS.md) to choose a session. Installing the project or running a queue check does not create permission for new social actions.
