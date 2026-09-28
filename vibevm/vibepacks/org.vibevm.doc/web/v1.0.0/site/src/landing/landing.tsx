/** @scope spec://org.vibevm.core/vibevm/common/PROP-057#SITE-ONE-SITE */

import { component$ } from "@qwik.dev/core";
import {
  CapabilityCard,
  CapabilityRow,
  DepGraph,
  Hero,
  InstallBlock,
} from "@vibe-docs/design";

import { docHref, href } from "../lib/href.ts";
import { LandingField } from "./field.tsx";
import {
  GITHUB_URL,
  GITVERSE_URL,
  INSTALL,
  type Locale,
  STRINGS,
  localePath,
} from "./i18n.ts";
import { LandingMap } from "./map.tsx";

/**
 * The landing itself: a hero with an install panel and a constellation,
 * then three cards that say what the thing is, then the header's
 * destinations drawn large, and the small print last.
 *
 * The route is a composition and nothing else — every element it places
 * comes from `design/`, and every word it places comes from `i18n.ts`.
 * That is the shape the port was aiming at: the same page the Astro site
 * serves, assembled out of the components the documentation is also
 * assembled from, so that a change to a button is one change (D-28).
 *
 * Two things joined it after the port, on the owner's word of 2026-09-26,
 * and both stand under everything the port moved: the map (`map.tsx`),
 * for the reader who does not read the words at the top of the page, and
 * the ground behind the whole page (`field.tsx`), which is what makes
 * the hero, the cards and the map one composition in the family's
 * suprematist language rather than a page with a picture at the bottom.
 * Neither touches a word or a position of the owner's own content.
 */
export type LandingProps = {
  readonly locale: Locale;
};

/**
 * The label the capabilities row carries for a screen reader.
 *
 * English on both pages, because it was English on both pages: the
 * Astro markup wrote it inline rather than through the string table and
 * the Russian page inherited it. Copied rather than fixed — the port
 * moves the landing as it is, and a string that was never translated is
 * the translator's to add, with a line in the string table to add it to
 * (F-74).
 */
const CAPABILITIES_LABEL = "What VibeVM is";

/** The id the install panel's heading carries, and its `aria-labelledby`. */
const INSTALL_HEADING_ID = "install-title";

/**
 * Where the release on the pill leads: the plan it is a point on (owner,
 * 2026-09-26). The page is the site's own, in the reader's language, and
 * its address is built like every other one here.
 */
function roadmapHref(locale: Locale): string {
  return href(`${localePath(locale)}roadmap/`);
}

/**
 * And the page of the manual the button beside it sends a reader to:
 * what the thing they are looking at is (owner, 2026-09-26).
 *
 * It is an address and not a string, built by the address map like every
 * other address on this site — the same page in the reader's own edition,
 * which for Russian is the source package under a language segment (D-06)
 * and never a package of its own.
 */
function guideHref(locale: Locale): string {
  return docHref({
    lang: locale === "en" ? null : locale,
    group: "org.vibevm.core",
    name: "vibevm-docs",
    version: "latest",
    document: "start/what-vibevm-is",
  });
}

/** The stable numbered install procedure, at the manual's Windows step. */
function manualInstallHref(locale: Locale): string {
  return (
    docHref({
      lang: locale === "en" ? null : locale,
      group: "org.vibevm.core",
      name: "vibevm-docs",
      version: "1.0.0",
      document: "start/install-vibe",
    }) + "#p09"
  );
}

export const Landing = component$<LandingProps>((props) => {
  const t = STRINGS[props.locale];
  return (
    <>
      {/* The ground first, so that it is behind everything in the flow of
          the document as well as in the stack: it is positioned against
          the page and takes no room in the column. */}
      <LandingField />
      <Hero
        eyebrow={t.eyebrow}
        headlineHtml={t.headlineHtml}
        leadHtml={t.leadHtml}
        /* What the project is properly called, who made it and what for
           (owner, 2026-09-27) — under the lead, in the lead's own measure
           and a quieter voice, because a reader who came for the software
           should meet the descriptor first and the name's history second. */
        noteHtml={t.nameNoteHtml}
        primary={{ label: t.ctaPrimary, href: GITHUB_URL }}
        secondary={{ label: t.ctaSecondary, href: GITVERSE_URL }}
        badge={t.badge}
        badgeHref={roadmapHref(props.locale)}
        badgeAction={{
          label: t.badgeAction,
          href: guideHref(props.locale),
        }}
      >
        <InstallBlock
          headingId={INSTALL_HEADING_ID}
          title={t.installTitle}
          lead={t.installLead}
          command={{
            label: t.installBash,
            prompt: INSTALL.bashPrompt,
            command: INSTALL.bashCommand,
          }}
          drawers={[
            {
              id: "windows",
              title: t.installWindows,
              description: t.installWindowsLead,
              commands: [
                {
                  label: t.installPowerShell,
                  prompt: INSTALL.powerShellPrompt,
                  command: INSTALL.powerShellCommand,
                },
                {
                  label: t.installCmd,
                  prompt: INSTALL.cmdPrompt,
                  command: INSTALL.cmdCommand,
                },
              ],
              links: [
                {
                  label: t.installManual,
                  description: t.installManualLead,
                  href: manualInstallHref(props.locale),
                  emphasis: "manual",
                },
              ],
            },
            {
              id: "releases",
              title: t.installReleases,
              description: t.installReleasesLead,
              links: [
                {
                  label: t.installBinaryReleases,
                  description: t.installBinaryReleasesLead,
                  href: `${GITHUB_URL}/releases`,
                },
                {
                  label: t.installSourceGitHub,
                  description: t.installSourceLead,
                  href: GITHUB_URL,
                },
                {
                  label: t.installSourceGitVerse,
                  description: t.installSourceLead,
                  href: GITVERSE_URL,
                },
              ],
            },
          ]}
          nextLabel={t.installNext}
          nextCommandHead={INSTALL.nextCommandHead}
          nextCommandTail={INSTALL.nextCommandTail}
          copyLabel={t.copyCommand}
          copiedLabel={t.copied}
        />
        <div q:slot="aside">
          <DepGraph />
        </div>
      </Hero>

      <CapabilityRow label={CAPABILITIES_LABEL}>
        {t.caps.map((cap) => (
          <CapabilityCard
            key={cap.label}
            label={cap.label}
            heading={cap.head}
            body={cap.body}
          />
        ))}
      </CapabilityRow>

      {/* Under everything the port moved and over the small print: the
          header's destinations, drawn large — the same list the header
          prints, for the reader who does not read the header. */}
      <LandingMap locale={props.locale} />

      {/* The small print, last on the page: which VibeVM this is not, and
          which AI Native Languages these are not. Search engines and
          model crawlers have been joining this project with the namesakes
          below, and a sentence that names both, with their addresses, is
          what an index can split them on.

          Three paragraphs and not one, in the order the owner gave them:
          each names one namesake, and a reader who has met only one of
          them should not have to read past the other two. None of them
          says anything ABOUT the other project beyond its name — what a
          namesake does is not this page's to describe — and none of them
          links to it. */}
      <p class="landing-disambiguation">{t.disambiguation}</p>
      <p class="landing-disambiguation">{t.disambiguationTgbyte}</p>
      <p class="landing-disambiguation">{t.disambiguationAiNative}</p>
    </>
  );
});
