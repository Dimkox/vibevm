/** @scope spec://org.vibevm.core/vibevm/common/PROP-057#SITE-ONE-SITE */

/**
 * The release the front door is showing, and the one way on beside it.
 *
 * The pill said «Early Access» and stood alone in a row with room to
 * spare; it now names the release — «Developer Preview 1», one name in
 * both languages, because a release name is not translated — and carries
 * beside it the link a reader who has just met the product wants: what
 * this thing is, in the manual, in the language they are reading (owner,
 * 2026-09-26).
 *
 * The address is asserted per language, because that is the half a test
 * is for: a button that led to the English page from the Russian landing
 * would look right on both.
 */

import { expect, test } from "@playwright/test";

const PAGES = [
  {
    route: "/",
    badge: "Developer Preview 1",
    roadmap: "/roadmap/",
    label: "What is VibeVM?",
    href: "/doc/org.vibevm.core/vibevm-docs/latest/start/what-vibevm-is/",
  },
  {
    route: "/ru/",
    badge: "Developer Preview 1",
    roadmap: "/ru/roadmap/",
    label: "Что такое VibeVM?",
    href: "/doc/ru/org.vibevm.core/vibevm-docs/latest/start/what-vibevm-is/",
  },
] as const;

for (const one of PAGES) {
  test(`${one.route} names the release on its pill`, async ({ page }) => {
    await page.goto(one.route);
    const pill = page.locator("main .hero__release");
    await expect(pill).toHaveText(one.badge);
    /* The dot stays: it is what makes the pill a pill. */
    await expect(pill.locator(".hero__release-dot")).toHaveCount(1);
  });
}

/**
 * And the pill leads to the plan the release is a point on (owner,
 * 2026-09-26), in the reader's own language.
 *
 * The ADDRESS is what is held here and not the page behind it: that page
 * is written on another branch and lands after this, and a test that
 * fetched it would be red about somebody else's work in progress.
 */
for (const one of PAGES) {
  test(`${one.route} sends the release to the roadmap`, async ({ page }) => {
    await page.goto(one.route);
    const pill = page.locator("main [data-hero-release]");
    await expect(pill).toHaveCount(1);
    await expect(pill).toHaveAttribute("href", one.roadmap);
    await expect(pill).toHaveClass(/hero__release/);

    /* A keyboard can see it, which is the half of «it is a control» that
       a look at the page does not prove. */
    await pill.focus();
    await expect(pill).toBeFocused();
    const outline = await pill.evaluate(
      (element) => getComputedStyle(element, ":focus-visible").outlineWidth,
    );
    expect(outline).not.toBe("0px");
  });
}

for (const one of PAGES) {
  test(`${one.route} offers the manual's answer beside it`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(one.route);

    const guide = page.locator("main .hero__run [data-hero-guide]");
    await expect(guide).toHaveCount(1);
    await expect(guide).toContainText(one.label);
    await expect(guide).toHaveAttribute("href", one.href);

    /* In the same row as the pill, and level with it: one line, two
       things, neither above the other. */
    const level = await page.evaluate(() => {
      const pill = document.querySelector(".hero__release");
      const link = document.querySelector("[data-hero-guide]");
      if (pill === null || link === null) return null;
      const one = pill.getBoundingClientRect();
      const other = link.getBoundingClientRect();
      return {
        beside: other.left > one.right,
        apart: Math.abs(
          one.top + one.height / 2 - (other.top + other.height / 2),
        ),
      };
    });
    expect(level?.beside).toBe(true);
    expect(level?.apart ?? 99).toBeLessThan(4);

    /* A keyboard can see where it is. */
    await guide.focus();
    await expect(guide).toBeFocused();
    const outline = await guide.evaluate(
      (element) => getComputedStyle(element, ":focus-visible").outlineWidth,
    );
    expect(outline).not.toBe("0px");
  });
}

/** On a phone the pair wraps instead of shrinking, and nothing overflows. */
for (const one of PAGES) {
  test(`${one.route} wraps the pair on a phone`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(one.route);

    const under = await page.evaluate(() => {
      const pill = document.querySelector(".hero__release");
      const link = document.querySelector("[data-hero-guide]");
      if (pill === null || link === null) return null;
      return (
        link.getBoundingClientRect().top >= pill.getBoundingClientRect().bottom
      );
    });
    expect(under).toBe(true);
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth >
          document.documentElement.clientWidth,
      ),
    ).toBe(false);
  });
}
