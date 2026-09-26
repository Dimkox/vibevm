# Changelog of the VibeVM manual {#root}

What changed for a reader, by date. This package carries one number and is republished under it in place, so a date and not a number says which edition a line belongs to. Written by hand from `JOURNAL.md`; the product's own versions are named where a change follows them.

## 1.0.0 — 2026-09-26

- **Long lines wrap.** Code, command output and the request at the top of a task page now wrap at the edge of their block instead of running off it; line breaks and indentation stay, and the copy button still copies the exact text.
- **The way on comes first.** A page now ends with the previous and the next page, the next one tinted to invite you on, then the rules the page cites, and only then the block written for agents.
- **Contents you can find.** On a phone or a tablet, Contents is now a button you can see and press; the ≡ button beside the text size opens the contents, and on a wide screen it brings the current page into view in the column beside it.
- **The advanced tutorial comes second.** On the learning path, Build Hello VibeVM in AI-Native Rust now follows Getting started directly.
- **The home page names the release.** Its pill reads Developer Preview 1 and leads to the roadmap; the button beside it opens What VibeVM is, in the page's language.
- **Your first project installs the redbook.** Create your first project now installs `org.vibevm.world/redbook`, shows the result in `vibe tree`, invites you to look at how the packages landed on disk, opens your agent inside the project, and writes the specification of a small calculator in Markdown, by hand or by asking the agent.
- **An advanced tutorial in AI-Native Rust.** Build Hello VibeVM in AI-Native Rust installs Rust on Windows, macOS or Linux, has the agent build the calculator from its specification, and shows how a changed rule leads a machine to every piece of code and every test that depended on it.
- **Page views are counted again.** The domain carries the same self-hosted Umami tag the old landing did, with no cookies and no personal data; the move to the documentation site had dropped it on 2026-09-12.
- **Words explain themselves.** On a wide screen, pointing at a word that links to the glossary shows its definition in a small card beside it; on a phone the link opens the glossary, as before. The manual now declares its glossary in its manifest, and the page for authors tells how to declare one.
- **Quotations fold.** A quotation from a specification now takes one line — a small triangle, `spec:` and a few words from the rule itself — and opens when you select it. A printed page and the `.md` and `.xml` versions of a page still carry every rule in full.

## 1.0.0 — 2026-09-25

- **The manual reads like a textbook.** The list beside a page follows a learning path: ten chapters from what VibeVM is and installing vibe, through everyday work, agents, the lifecycle and writing packages, to the appendices, with the glossary last. A switch above the list brings back the grouping by section, and every page ends with the previous and the next page on the path.

## 1.0.0 — 2026-09-14

What is new for a reader since the pages were first laid out:

- **The pages open in the dark, and a switch keeps the other theme.** The choice is remembered on the reader's own machine and is sent nowhere.
- **Search finds a page by a word from it.** The box reaches the title and the leading fact of every page and of every documentation on the site; it asks no search service, because the index is part of the site.
- **A card says what it stands for.** It now wears the mark of its package's kind, the hand that wrote its prose, and, for a bridge, the two authorships kept apart — where one drawing stood before that distinguished nothing.
- **Keeping `vibe` current is written down.** `self update` follows where the running copy came from, `self reinstall` fetches the running version again without changing which one it is, and `self rollback` goes back.
- **The manual reads in Russian.** The adaptation is a package of its own, `vibevm-docs-ru`, mirroring these pages block for block in its own sentences.

## 1.0.0 — the first edition

The first complete manual of VibeVM 1.0, forty-nine pages in English:

- **Start** — what VibeVM is, installing vibe, a first project, what a project contains.
- **The model** — the two trees, the boot lane, packages and their eight kinds, registries, versions, the lock file and the store, dependency visibility.
- **How-to** — setting up a workspace, working offline, private registries, publishing a package, the lifecycle from build to deploy.
- **Agents** — asking your agent to do the work, giving it the vibevm skill, how agents read this manual.
- **Authoring** — writing packages of every kind, flows, feats and stacks, language packages, tools and MCP servers, documentation and its adaptations, bridging a repository, facts and status markers, the specifications agents can cite.
- **Reference** — every command's help, the manifest and the lock file, machine formats, the dependency tree, the diagnostics and their fixes.
- **Architecture** — how vibe is built, traceability between specs and code, what the lifecycle epic delivered, how this manual is maintained.
- **Glossary and questions.**

Every task page opens with the request you give a coding agent; every example on these pages is run against the real binary before a release; every rule quotes the specification by its address.

Not in this edition: the Russian adaptation (it follows as its own package), images for the package card (placeholders stand in), and the third level of command help (`vibe doc build --help` and its siblings are described in prose).
