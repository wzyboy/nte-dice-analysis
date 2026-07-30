---
name: update-nte-known-items
description: Update src/nte_dice_analysis/known_items.toml from paired official NTE (异环) Bilibili announcements for a new 限定棋盘 and 弧盘研募 banner. Use when the user supplies the two announcement URLs or pasted announcement text and wants exact banner item names extracted, normalized to this repository's conventions, inserted into the rotating known-item sections, and validated.
---

# Update NTE Known Items

Update only the rotating banner blocks in
`src/nte_dice_analysis/known_items.toml`. Treat the official announcement text
as the authority for spelling. Preserve the file's existing structure,
comments, ordering, quoting, and unrelated entries.

## Required inputs

Obtain both announcements for the banner cycle:

1. One official `限定棋盘` announcement.
2. One official `弧盘研募` announcement.

Accept Bilibili URLs, pasted text, or a mixture. Also establish the game version
used in the TOML comments, such as `1.2`. Use a version stated by the user or
verified from an official source. If it cannot be established reliably, ask
the user instead of inferring it solely from chronology.

## Retrieve authoritative text

For each URL:

1. Try to open it with the available web-reading tool.
2. If direct access is blocked, search the web for the exact URL, post title,
   or distinctive official wording, restricted to official Bilibili results
   when possible.
3. Confirm that the source identifies the author as `异环` and that its title
   and body describe the expected banner type.
4. Do not use `curl`, repeated scraping attempts, or raw Bilibili HTML as the
   primary extraction path. Bilibili may return anti-scraping or script-only
   pages.
5. Do not use a third-party repost as authority for exact spelling unless the
   user explicitly approves it.
6. If authoritative text remains inaccessible or incomplete, stop before
   editing and ask the user to copy-paste the affected official post text.

Web-search snippets are acceptable only when they expose all required wording
from the official post unambiguously.

## Verify the pair

Before editing, confirm:

- The limited post is titled like `「<棋盘名>」限定棋盘即将开启`.
- The arc post is titled like `「<特刊名>」弧盘研募计划即将开启`.
- Their opening periods identify them as the intended pair.
- Neither banner block is already present with the same source URL or banner
  name.

If the periods do not correspond, or the user appears to have supplied posts
from different banner cycles, report the mismatch and request the correct
post. If a block already exists, reconcile only a demonstrated spelling error;
do not append a duplicate.

## Extract the limited-board block

Extract exactly four rotating items. Ignore featured A-grade characters,
dice, keys, pity rules, event rewards, and quoted names elsewhere in the post.

Use these semantic anchors:

- Limited S character: `当期限定S级角色「<角色>」`
- Glider: `滑翔翼涂装「<滑翔翼>」`
- Vehicle modification: a non-glider vehicle/model followed by
  `涂装「<改装件>」`
- Outfit: `<角色>时装「<时装>」`

Write them in this fixed order and representation:

```toml
# <version> <棋盘名> <limited-post-url>
"角色·<角色>",
"时装·<时装>",
"改装件·<改装件>-涂装",
"滑翔翼·<滑翔翼>",
```

For example, the official `无归路` wording yields:

```toml
"角色·卡厄斯",
"时装·放晴日",
"改装件·猎犬奔袭-涂装",
"滑翔翼·天际猎手",
```

Do not include the vehicle model (`Novis ST-X 950` in that example) in the
stored modification name.

## Extract the arc-recruitment block

Extract the single name from `当期限定S级弧盘「<弧盘>」` and write:

```toml
# <version> <特刊名> <arc-post-url>
"<弧盘>",
```

For example, the official `决意特刊` wording yields:

```toml
"穿过胭红蜃景",
```

Arc recruitment displays bare item names, so do not add the `弧盘·` prefix.

## Preserve exact names

- Copy Chinese characters exactly; do not silently substitute homophones,
  variants, or visually similar characters.
- Strip only the announcement's outer prose delimiters around a name.
- Preserve punctuation that is part of the item name, including nested book
  title marks or quotation marks.
- Do not infer a name from the banner title, character identity, vehicle
  model, prior leaks, or a previous banner.
- Cross-check repeated occurrences within the same official post. If they
  disagree, pause and report the ambiguity.

## Edit the TOML

- Insert each block chronologically in its existing rotating section.
- Keep limited-board entries under `[pools."限定棋盘"]`.
- Keep the bare arc name under `[pools."弧盘研募"]`.
- Keep the commented future-banner template commented and below real limited
  banner entries.
- Preserve UTF-8 text, four-space indentation, double-quoted TOML strings,
  trailing commas, and the exact source URLs supplied by the user.
- Do not modify `[pools."标准棋盘"]`.
- Do not commit changes unless the user explicitly requests a commit.

## Validate and report

1. Parse the updated TOML through the project's existing loader.
2. Check for duplicate item strings within each pool.
3. Inspect the diff and verify that only the intended banner blocks changed.
4. Report the two banner names, extracted item mapping, source URLs, and test
   result. Clearly disclose any spelling or source ambiguity.
