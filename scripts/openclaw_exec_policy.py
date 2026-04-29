#!/usr/bin/env python3
"""OpenClaw exec allowlist policy.

Schema (enforced by scripts/validate_openclaw_config.py):
  Each profile must have:
    - minPositional: int
    - maxPositional: int
    - allowedValueFlags: list[str] — must start with '--'

Note on short flags: the schema only validates long flags starting with '--'.
It's unclear whether the runtime gateway also rejects short flags like '-la'
or bare long booleans not in allowedValueFlags. We default to listing the
long-form equivalents of common flags so cody can fall back to '--all'
instead of '-a' if short flags are blocked at runtime. Verify empirically
when touching these profiles.

Layout:
  - SAFE_BIN_PROFILES           — cody's original first-party tools (unchanged).
  - SHELL_UTILITY_PROFILES      — read-only / inspection shell utilities.
  - DEV_TOOL_PROFILES           — git + language runtimes for scripting + self-refresh.
  - FS_WRITE_PROFILES           — non-destructive filesystem writes (mkdir/touch/cp/mv).
  - NETWORK_FETCH_PROFILES      — curl/wget for fetching skills + updates.
  - AWS_PROFILES                — aws CLI (AWS_PROFILE=technibears comes from shell env).
  - AUDIO_MEDIA_PROFILES        — ffmpeg/ffprobe/sox/whisper/opusenc/afplay/say.
  - ARCHIVE_TRANSPORT_PROFILES  — tar/gzip/zip/rsync/ssh-keygen.
  - ROOT_ONLY_SAFE_BIN_PROFILES — only added when include_root_admin=True.

Intentionally NOT in the allowlist (must go through ask/on-miss):
  rm, chmod, chown, ssh, nc, scp  — destructive or lateral-movement risk.
"""

from __future__ import annotations

from copy import deepcopy

# ---------------------------------------------------------------------------
# First-party cody tools (original profiles — do not edit).
# ---------------------------------------------------------------------------
SAFE_BIN_PROFILES = {
    "memory-read": {
        "minPositional": 0,
        "maxPositional": 0,
        "allowedValueFlags": ["--query", "--as-of", "--limit", "--include-history", "--json"],
    },
    "memory-write": {
        "minPositional": 0,
        "maxPositional": 0,
        "allowedValueFlags": [
            "--entity",
            "--entity-type",
            "--predicate",
            "--value",
            "--target-entity",
            "--target-type",
            "--source",
            "--source-type",
            "--quote",
            "--confidence",
            "--json",
        ],
    },
    "outlook-read": {
        "minPositional": 0,
        "maxPositional": 0,
        "allowedValueFlags": ["--list", "--message", "--limit", "--json"],
    },
    "outlook-draft": {
        "minPositional": 0,
        "maxPositional": 0,
        "allowedValueFlags": ["--to", "--subject", "--body", "--cc", "--content-type", "--json"],
    },
    "outlook-queue-send": {
        "minPositional": 0,
        "maxPositional": 0,
        "allowedValueFlags": ["--draft-id", "--to", "--subject", "--preview", "--web-link", "--session-id", "--thread-id", "--json"],
    },
    "outlook-send-approved": {
        "minPositional": 0,
        "maxPositional": 0,
        "allowedValueFlags": ["--draft-id", "--json"],
    },
}

ROOT_ONLY_SAFE_BIN_PROFILES = {
    "cody-admin": {
        "minPositional": 0,
        "maxPositional": 0,
        "allowedValueFlags": ["--status", "--restart", "--refresh-snapshot", "--pull-latest", "--json"],
    }
}

# ---------------------------------------------------------------------------
# Shell utility profiles — inspection / read / basic text processing.
# maxPositional=50 is generous so multi-file ops (`cat a b c ...`) work.
# ---------------------------------------------------------------------------
SHELL_UTILITY_PROFILES = {
    "sudo": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--user", "--group", "--set-home", "--preserve-env", "--login", "--non-interactive"
        ],
    },
    "ls": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--all", "--almost-all", "--long", "--human-readable", "--recursive",
            "--reverse", "--sort", "--time", "--classify", "--color", "--width",
            "--format", "--directory", "--inode", "--size", "--time-style",
            "--group-directories-first", "--hide", "--ignore",
        ],
    },
    "cat": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--number", "--number-nonblank", "--show-ends", "--show-tabs",
            "--show-nonprinting", "--squeeze-blank", "--show-all",
        ],
    },
    "head": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--lines", "--bytes", "--quiet", "--verbose", "--zero-terminated"],
    },
    "tail": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--lines", "--bytes", "--follow", "--retry", "--pid",
            "--sleep-interval", "--quiet", "--verbose", "--zero-terminated",
            "--max-unchanged-stats",
        ],
    },
    "wc": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--lines", "--words", "--chars", "--bytes", "--max-line-length",
            "--files0-from",
        ],
    },
    "grep": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--regexp", "--file", "--ignore-case", "--word-regexp", "--line-regexp",
            "--extended-regexp", "--fixed-strings", "--basic-regexp", "--perl-regexp",
            "--count", "--files-with-matches", "--files-without-match", "--only-matching",
            "--quiet", "--silent", "--max-count", "--context", "--before-context",
            "--after-context", "--invert-match", "--recursive", "--dereference-recursive",
            "--include", "--exclude", "--exclude-dir", "--exclude-from",
            "--color", "--colour", "--line-number", "--with-filename", "--no-filename",
            "--null-data", "--binary-files", "--label", "--initial-tab",
            "--devices", "--directories", "--group-separator",
        ],
    },
    "find": {
        "minPositional": 0, "maxPositional": 50,
        # find uses single-dash long options (-name, -type, -exec). They are not
        # "long flags" per this schema. If the runtime blocks them, find will be
        # crippled. Only the GNU double-dash flags are listed here.
        "allowedValueFlags": ["--help", "--version", "--maxdepth", "--mindepth"],
    },
    "stat": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--format", "--printf", "--terse", "--dereference", "--file-system",
            "--cached",
        ],
    },
    "file": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--brief", "--mime", "--mime-type", "--mime-encoding", "--files-from",
            "--preserve-date", "--raw", "--print0", "--no-pad", "--special-files",
            "--magic-file", "--compile", "--exclude", "--extension", "--separator",
        ],
    },
    "which": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--all", "--skip-alias", "--read-alias", "--skip-dot", "--skip-tilde"],
    },
    "echo": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [],
    },
    "date": {
        "minPositional": 0, "maxPositional": 5,
        "allowedValueFlags": [
            "--date", "--reference", "--iso-8601", "--rfc-2822", "--rfc-3339",
            "--utc", "--set", "--file", "--universal",
        ],
    },
    "basename": {
        "minPositional": 0, "maxPositional": 5,
        "allowedValueFlags": ["--multiple", "--suffix", "--zero"],
    },
    "dirname": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--zero"],
    },
    "tr": {
        "minPositional": 0, "maxPositional": 5,
        "allowedValueFlags": ["--complement", "--delete", "--squeeze-repeats", "--truncate-set1"],
    },
    "awk": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--field-separator", "--file", "--assign", "--source", "--include",
            "--load", "--posix", "--traditional", "--bignum", "--non-decimal-data",
            "--characters-as-bytes", "--dump-variables", "--gen-pot",
            "--lint", "--no-optimize", "--optimize", "--profile", "--re-interval",
            "--sandbox", "--use-lc-numeric", "--pretty-print",
        ],
    },
    "sed": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--expression", "--file", "--in-place", "--regexp-extended",
            "--quiet", "--silent", "--separate", "--unbuffered", "--null-data",
            "--debug", "--follow-symlinks", "--sandbox", "--line-length",
            "--posix",
        ],
    },
    "cut": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--bytes", "--characters", "--fields", "--delimiter", "--complement",
            "--only-delimited", "--output-delimiter", "--zero-terminated",
        ],
    },
    "sort": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--ignore-leading-blanks", "--dictionary-order", "--ignore-case",
            "--general-numeric-sort", "--human-numeric-sort", "--ignore-nonprinting",
            "--month-sort", "--numeric-sort", "--random-sort", "--reverse",
            "--version-sort", "--key", "--field-separator", "--stable", "--unique",
            "--output", "--zero-terminated", "--buffer-size", "--compress-program",
            "--parallel", "--temporary-directory", "--files0-from", "--check",
            "--merge", "--batch-size", "--debug", "--random-source",
        ],
    },
    "uniq": {
        "minPositional": 0, "maxPositional": 5,
        "allowedValueFlags": [
            "--count", "--repeated", "--all-repeated", "--skip-fields",
            "--ignore-case", "--skip-chars", "--unique", "--zero-terminated",
            "--check-chars", "--group",
        ],
    },
    "xargs": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--arg-file", "--delimiter", "--replace", "--max-lines", "--max-args",
            "--max-procs", "--interactive", "--process-slot-var", "--no-run-if-empty",
            "--eof", "--max-chars", "--verbose", "--null", "--exit",
            "--show-limits",
        ],
    },
    "pwd": {
        "minPositional": 0, "maxPositional": 0,
        "allowedValueFlags": ["--logical", "--physical"],
    },
    "env": {
        # env is frequently used to prefix commands: `env AWS_PROFILE=technibears aws ...`
        # Positionals carry both VAR=VALUE pairs and the invoked binary + its args.
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--ignore-environment", "--null", "--unset", "--chdir", "--split-string",
            "--block-signal", "--default-signal", "--ignore-signal",
            "--list-signal-handling", "--argv0",
        ],
    },
    "readlink": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--canonicalize", "--canonicalize-existing", "--canonicalize-missing",
            "--no-newline", "--quiet", "--silent", "--verbose", "--zero",
        ],
    },
    "realpath": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--canonicalize-existing", "--canonicalize-missing", "--logical",
            "--physical", "--quiet", "--relative-to", "--relative-base",
            "--strip", "--zero",
        ],
    },
    "tee": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--append", "--ignore-interrupts", "--output-error"],
    },
    "less": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--help", "--version"],
    },
    "more": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--help", "--version"],
    },
    "diff": {
        "minPositional": 0, "maxPositional": 10,
        "allowedValueFlags": [
            "--brief", "--report-identical-files", "--recursive", "--unified",
            "--context", "--ignore-case", "--ignore-tab-expansion",
            "--ignore-space-change", "--ignore-all-space", "--ignore-blank-lines",
            "--ignore-matching-lines", "--text", "--binary", "--color",
            "--exclude", "--exclude-from", "--starting-file", "--from-file",
            "--to-file", "--label", "--new-file", "--unidirectional-new-file",
            "--initial-tab", "--tabsize", "--expand-tabs", "--suppress-common-lines",
            "--side-by-side", "--width", "--speed-large-files",
            "--strip-trailing-cr", "--no-dereference", "--show-c-function",
            "--show-function-line",
        ],
    },
    "comm": {
        "minPositional": 0, "maxPositional": 5,
        "allowedValueFlags": [
            "--check-order", "--nocheck-order", "--output-delimiter",
            "--zero-terminated", "--total",
        ],
    },
    "paste": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--delimiters", "--serial", "--zero-terminated"],
    },
    "column": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--table", "--separator", "--output-separator", "--table-columns",
            "--table-hide", "--fillrows", "--json", "--tree", "--tree-id",
            "--tree-parent", "--table-name", "--table-order", "--table-right",
            "--table-truncate", "--table-wrap", "--table-empty-lines",
            "--table-noheadings", "--table-header-repeat",
        ],
    },
    "fold": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--bytes", "--spaces", "--width"],
    },
    "fmt": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--crown-margin", "--prefix", "--split-only", "--tagged-paragraph",
            "--uniform-spacing", "--width", "--goal",
        ],
    },
    "expand": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--initial", "--tabs"],
    },
    "unexpand": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--all", "--first-only", "--tabs"],
    },
    "nl": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--body-numbering", "--section-delimiter", "--footer-numbering",
            "--header-numbering", "--line-increment", "--join-blank-lines",
            "--number-format", "--no-renumber", "--number-separator",
            "--starting-line-number", "--number-width",
        ],
    },
    "od": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--address-radix", "--skip-bytes", "--read-bytes", "--endian",
            "--strings", "--format", "--output-duplicates", "--width",
            "--traditional",
        ],
    },
    "hexdump": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--one-byte-octal", "--one-byte-char", "--canonical",
            "--two-bytes-decimal", "--two-bytes-octal", "--two-bytes-hex",
            "--format", "--format-file", "--length", "--skip", "--no-squeezing",
            "--color",
        ],
    },
    "jq": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--arg", "--argjson", "--args", "--jsonargs", "--slurpfile",
            "--rawfile", "--indent", "--tab", "--compact-output", "--null-input",
            "--raw-input", "--slurp", "--raw-output", "--raw-output0",
            "--join-output", "--ascii-output", "--sort-keys", "--unbuffered",
            "--seq", "--stream", "--stream-errors", "--exit-status",
        ],
    },
    "yq": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--arg", "--input-format", "--output-format", "--indent",
            "--tojson", "--yaml-output", "--yaml-roundtrip", "--in-place",
            "--from-file", "--null-input", "--raw-output", "--slurp",
        ],
    },
}

# ---------------------------------------------------------------------------
# Dev / scripting tools.
# ---------------------------------------------------------------------------
DEV_TOOL_PROFILES = {
    # git gets a broad flag set so cody can run status/log/diff/commit/push/pull
    # without being blocked. This is deliberate: cody is a developer agent and
    # needs to manage its own repo state for self-refresh.
    "git": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            # top-level git options
            "--git-dir", "--work-tree", "--namespace", "--super-prefix",
            "--exec-path", "--config-env", "--literal-pathspecs",
            "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs",
            "--no-optional-locks", "--no-replace-objects", "--bare",
            # common subcommand options (log/commit/push/diff/branch/checkout/merge/rebase)
            "--message", "--amend", "--author", "--date", "--file",
            "--branch", "--branches", "--force", "--force-with-lease",
            "--tags", "--depth", "--unshallow", "--shallow-since",
            "--shallow-exclude", "--recurse-submodules", "--no-recurse-submodules",
            "--set-upstream-to", "--set-upstream", "--track", "--no-track",
            "--remote", "--delete", "--move", "--copy", "--list",
            "--verbose", "--quiet", "--oneline", "--graph", "--all",
            "--since", "--until", "--pretty", "--format", "--stat",
            "--name-only", "--name-status", "--summary", "--abbrev-commit",
            "--abbrev", "--no-merges", "--merges", "--first-parent",
            "--follow", "--diff-filter", "--patch", "--no-patch", "--unified",
            "--ignore-all-space", "--ignore-space-change", "--ignore-space-at-eol",
            "--word-diff", "--word-diff-regex", "--color", "--no-color",
            "--color-words", "--cached", "--staged", "--index", "--check",
            "--raw", "--reverse", "--files", "--files-with-matches",
            "--line-number", "--count", "--heading", "--break", "--context",
            "--function-context", "--strategy", "--strategy-option",
            "--no-ff", "--ff-only", "--squash", "--commit", "--no-commit",
            "--log", "--no-edit", "--edit", "--allow-empty",
            "--allow-empty-message", "--gpg-sign", "--no-gpg-sign",
            "--signoff", "--no-signoff", "--sign", "--no-sign",
            "--pathspec-from-file", "--pathspec-file-nul",
            "--include", "--exclude", "--exclude-standard",
            "--others", "--ignored", "--modified", "--deleted",
            "--untracked-files", "--ignore-submodules", "--porcelain",
            "--short", "--long", "--column", "--no-column",
            "--merged", "--no-merged", "--contains", "--no-contains",
            "--points-at", "--sort", "--describe", "--tag",
            "--no-tags", "--prune", "--no-prune", "--keep", "--no-keep",
            "--atomic", "--no-atomic", "--push-option", "--receive-pack",
            "--upload-pack", "--progress", "--no-progress",
            "--rebase", "--no-rebase", "--ff", "--no-ff-only",
            "--autosquash", "--no-autosquash", "--autostash", "--no-autostash",
            "--interactive", "--no-interactive", "--onto", "--root",
            "--reset-author", "--allow-unrelated-histories",
            "--dry-run", "--force-rebase", "--no-force-rebase",
            "--preserve-merges", "--rebase-merges", "--keep-base",
            "--empty", "--committer-date-is-author-date", "--ignore-date",
            "--skip", "--abort", "--continue", "--edit-todo", "--show-current-patch",
            "--whitespace", "--ignore-whitespace", "--no-stat",
            "--tee", "--no-tee",
            "--mirror", "--all", "--prune-tags",
            "--recursive", "--merge-base",
        ],
    },
    "python3": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--version", "--help", "--check-hash-based-pycs"],
    },
    "python": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--version", "--help", "--check-hash-based-pycs"],
    },
    "pip": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--requirement", "--constraint", "--no-deps", "--pre", "--editable",
            "--dry-run", "--target", "--platform", "--python-version",
            "--implementation", "--abi", "--user", "--root", "--prefix", "--src",
            "--upgrade", "--upgrade-strategy", "--force-reinstall",
            "--ignore-installed", "--ignore-requires-python",
            "--no-build-isolation", "--use-pep517", "--no-use-pep517",
            "--check-build-dependencies", "--break-system-packages",
            "--no-compile", "--no-warn-script-location", "--no-warn-conflicts",
            "--no-binary", "--only-binary", "--prefer-binary", "--require-hashes",
            "--progress-bar", "--root-user-action", "--report", "--no-clean",
            "--index-url", "--extra-index-url", "--no-index", "--find-links",
            "--proxy", "--retries", "--timeout", "--exists-action",
            "--trusted-host", "--cert", "--client-cert", "--cache-dir",
            "--no-cache-dir", "--disable-pip-version-check", "--no-color",
            "--no-python-version-warning", "--use-feature", "--use-deprecated",
            "--verbose", "--quiet", "--log", "--debug", "--format", "--outdated",
            "--uptodate", "--editable", "--local", "--path",
            "--not-required", "--exclude-editable", "--include-editable",
            "--exclude",
        ],
    },
    "node": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--version", "--help", "--eval", "--print", "--check",
            "--require", "--import", "--experimental-modules",
            "--experimental-vm-modules", "--experimental-worker",
            "--no-warnings", "--max-old-space-size", "--max-semi-space-size",
            "--optimize-for-size", "--unhandled-rejections", "--conditions",
            "--input-type", "--enable-source-maps", "--inspect", "--inspect-brk",
            "--inspect-port", "--watch", "--watch-path", "--trace-warnings",
            "--trace-uncaught", "--trace-exit", "--trace-atomics-wait",
            "--title", "--heap-prof", "--heap-prof-dir", "--heap-prof-interval",
            "--heap-prof-name", "--redirect-warnings", "--report-dir",
            "--report-directory", "--report-filename", "--report-signal",
            "--stack-trace-limit", "--tls-cipher-list", "--tls-keylog",
            "--tls-max-v1.2", "--tls-max-v1.3", "--tls-min-v1.0", "--tls-min-v1.1",
            "--tls-min-v1.2", "--tls-min-v1.3", "--use-bundled-ca",
            "--use-openssl-ca",
        ],
    },
    "npm": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--global", "--save", "--save-dev", "--save-optional", "--save-peer",
            "--save-exact", "--save-prefix", "--save-bundle", "--registry",
            "--scope", "--prefix", "--production", "--omit", "--include",
            "--only", "--dry-run", "--force", "--ignore-scripts",
            "--legacy-peer-deps", "--strict-peer-deps", "--package-lock-only",
            "--no-package-lock", "--workspace", "--workspaces",
            "--include-workspace-root", "--if-present",
            "--tag", "--access", "--otp", "--loglevel", "--quiet", "--silent",
            "--verbose", "--json", "--long", "--parseable", "--depth",
            "--all", "--link", "--no-audit", "--audit-level", "--fund",
            "--no-fund", "--dev", "--prod", "--offline", "--prefer-offline",
            "--prefer-online",
        ],
    },
    "npx": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--package", "--call", "--cache", "--prefer-online", "--prefer-offline",
            "--offline", "--registry", "--yes", "--no", "--no-install",
            "--ignore-existing", "--shell", "--shell-auto-fallback",
        ],
    },
}

# ---------------------------------------------------------------------------
# Non-destructive filesystem writes.
# Deliberately omits: rm, chmod, chown — those require explicit ask/on-miss.
# ---------------------------------------------------------------------------
FS_WRITE_PROFILES = {
    "mkdir": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--mode", "--parents", "--verbose", "--context"],
    },
    "touch": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--no-create", "--date", "--reference", "--time", "--no-dereference",
        ],
    },
    "cp": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--archive", "--attributes-only", "--backup", "--force",
            "--interactive", "--no-clobber", "--dereference", "--no-dereference",
            "--link", "--preserve", "--no-preserve", "--parents", "--recursive",
            "--reflink", "--remove-destination", "--sparse",
            "--strip-trailing-slashes", "--symbolic-link", "--suffix",
            "--target-directory", "--no-target-directory", "--update",
            "--verbose", "--one-file-system", "--context",
        ],
    },
    "mv": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--backup", "--force", "--interactive", "--no-clobber",
            "--strip-trailing-slashes", "--suffix", "--target-directory",
            "--no-target-directory", "--update", "--verbose", "--context",
        ],
    },
}

# ---------------------------------------------------------------------------
# Network fetch.
# Deliberately omits: ssh, nc, scp — lateral movement risk.
# ---------------------------------------------------------------------------
NETWORK_FETCH_PROFILES = {
    "curl": {
        "minPositional": 0, "maxPositional": 10,
        "allowedValueFlags": [
            "--url", "--request", "--header", "--data", "--data-binary",
            "--data-urlencode", "--data-raw", "--form", "--form-string",
            "--user", "--user-agent", "--referer", "--cookie", "--cookie-jar",
            "--location", "--location-trusted", "--max-redirs", "--max-time",
            "--connect-timeout", "--retry", "--retry-delay", "--retry-max-time",
            "--retry-connrefused", "--retry-all-errors",
            "--output", "--remote-name", "--remote-name-all",
            "--remote-header-name", "--output-dir", "--create-dirs",
            "--silent", "--show-error", "--verbose", "--insecure",
            "--cacert", "--capath", "--cert", "--cert-type", "--key",
            "--key-type", "--tlsv1", "--tlsv1.2", "--tlsv1.3",
            "--http1.0", "--http1.1", "--http2", "--http2-prior-knowledge",
            "--http3", "--proxy", "--proxy-user", "--proxy-header",
            "--noproxy", "--compressed", "--head", "--include",
            "--fail", "--fail-with-body", "--range", "--write-out",
            "--config", "--resolve", "--dns-servers", "--interface",
            "--socks5", "--socks5-hostname", "--parallel", "--parallel-max",
            "--next", "--continue-at", "--upload-file",
            "--basic", "--digest", "--ntlm", "--negotiate", "--anyauth",
            "--oauth2-bearer", "--aws-sigv4",
        ],
    },
    "wget": {
        "minPositional": 0, "maxPositional": 10,
        "allowedValueFlags": [
            "--output-document", "--output-file", "--append-output", "--debug",
            "--quiet", "--verbose", "--no-verbose", "--input-file",
            "--force-html", "--base", "--config", "--tries", "--timeout",
            "--dns-timeout", "--connect-timeout", "--read-timeout", "--wait",
            "--waitretry", "--random-wait", "--user", "--password",
            "--user-agent", "--post-data", "--post-file", "--method",
            "--body-data", "--body-file", "--header", "--max-redirect",
            "--proxy-user", "--proxy-password", "--referer", "--save-cookies",
            "--load-cookies", "--keep-session-cookies", "--no-cookies",
            "--no-check-certificate", "--certificate", "--certificate-type",
            "--private-key", "--private-key-type", "--ca-certificate",
            "--ca-directory", "--secure-protocol", "--ciphers",
            "--directory-prefix", "--cut-dirs", "--recursive", "--level",
            "--no-parent", "--accept", "--reject", "--domains",
            "--exclude-domains", "--include-directories", "--exclude-directories",
            "--limit-rate", "--retry-connrefused", "--content-disposition",
            "--trust-server-names", "--continue", "--progress", "--show-progress",
        ],
    },
}

# ---------------------------------------------------------------------------
# AWS CLI.
# AWS_PROFILE=technibears is expected to come from the environment (systemd unit,
# shell init, or explicit `env AWS_PROFILE=technibears aws ...`). The exec
# policy schema has no env-var field, so we only whitelist the binary and
# its common top-level flags.
# ---------------------------------------------------------------------------
AWS_PROFILES = {
    "aws": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--profile", "--region", "--output", "--endpoint-url", "--query",
            "--cli-input-json", "--cli-input-yaml", "--cli-binary-format",
            "--cli-read-timeout", "--cli-connect-timeout", "--cli-auto-prompt",
            "--no-cli-auto-prompt", "--color", "--debug", "--no-sign-request",
            "--no-verify-ssl", "--no-paginate", "--page-size", "--max-items",
            "--starting-token", "--ca-bundle", "--version",
        ],
    },
}

# ---------------------------------------------------------------------------
# Audio / media toolchain.
#
# Short-flag caveat: ffmpeg/ffprobe/sox all use single-dash options (-i, -c:a,
# -b:a, -ar). The schema's `allowedValueFlags` only validates `--`-prefixed
# flags. If the runtime gateway also rejects single-dash long options, these
# bins will be effectively crippled for anything beyond bare positional args.
# Verify with a real transcode after deploy; if broken, may need to downgrade
# to ask/on-miss or lobby OpenClaw for a short-flag profile extension.
#
# Note on stt-wrapper path: voicenote transcription runs under the openclaw
# system user, invoked by OpenClaw's media-understanding plugin via the
# audio.transcription.command path in the rendered config. It does NOT go
# through the safeBin path, so whisper-ctranslate2 doesn't strictly need to
# be listed here. It's included anyway so cody skills can invoke it directly
# if needed (e.g. for skill-side audio analysis).
# ---------------------------------------------------------------------------
AUDIO_MEDIA_PROFILES = {
    "ffmpeg": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--help", "--version",
            # Most ffmpeg flags are single-dash; listing the few long-form
            # accepted variants for completeness.
        ],
    },
    "ffprobe": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--help", "--version"],
    },
    "sox": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--help", "--version", "--help-effect"],
    },
    "afplay": {
        # macOS built-in audio playback. Short-flag only (-v, -q, -t, -r, -d).
        "minPositional": 0, "maxPositional": 10,
        "allowedValueFlags": ["--help", "--version"],
    },
    "say": {
        # macOS text-to-speech. Supports both short and long flags.
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--voice", "--rate", "--output-file", "--file-format",
            "--data-format", "--channels", "--quality", "--progress",
            "--input-file", "--network-send", "--interactive",
        ],
    },
    "whisper": {
        # Upstream openai/whisper Python CLI. Uses long flags.
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--model", "--model_dir", "--device", "--output_dir",
            "--output_format", "--verbose", "--task", "--language",
            "--temperature", "--best_of", "--beam_size", "--patience",
            "--length_penalty", "--suppress_tokens", "--initial_prompt",
            "--condition_on_previous_text", "--fp16", "--threads",
            "--clip_timestamps", "--hallucination_silence_threshold",
        ],
    },
    "whisper-cli": {
        # whisper.cpp CLI. Mostly short flags but some long forms.
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--help", "--version", "--model", "--file", "--output-txt",
            "--output-vtt", "--output-srt", "--output-json", "--language",
            "--translate", "--threads", "--processors", "--no-timestamps",
            "--no-gpu",
        ],
    },
    "whisper-ctranslate2": {
        # faster-whisper / ctranslate2 wrapper. Long flags throughout.
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--model", "--model_directory", "--device", "--compute_type",
            "--threads", "--task", "--beam_size", "--output_format",
            "--output_dir", "--verbose", "--language", "--temperature",
            "--patience", "--best_of", "--condition_on_previous_text",
            "--vad_filter", "--vad_threshold", "--vad_min_speech_duration_ms",
            "--vad_min_silence_duration_ms", "--word_timestamps",
            "--highlight_words", "--hallucination_silence_threshold",
            "--hf_token", "--local_files_only",
        ],
    },
    "opusenc": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--help", "--version", "--quiet", "--bitrate", "--vbr", "--cvbr",
            "--hard-cbr", "--framesize", "--expect-loss", "--comp",
            "--max-delay", "--raw", "--raw-bits", "--raw-rate", "--raw-chan",
            "--raw-endianness", "--title", "--artist", "--album", "--tracknumber",
            "--genre", "--date", "--comment", "--padding", "--discard-comments",
            "--discard-pictures", "--picture",
        ],
    },
    "opusdec": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--help", "--version", "--quiet", "--rate", "--force-stereo",
            "--gain", "--no-dither", "--float", "--force-wav", "--packet-loss",
            "--save-range",
        ],
    },
}

# ---------------------------------------------------------------------------
# Archive / transport tools.
# tar, gzip, zip — safe for read/write within allowed paths.
# rsync — great for structured copies; excluding --rsh/--remote-shell usage
# would need schema extension, but the basic local/remote usage works.
# ssh-keygen — generating keys is read-only on the network side; no egress
# until/unless a private key is used by ssh (which remains behind ask/on-miss).
# ---------------------------------------------------------------------------
ARCHIVE_TRANSPORT_PROFILES = {
    "tar": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--create", "--extract", "--list", "--append", "--update",
            "--delete", "--concatenate", "--diff", "--compare",
            "--file", "--directory", "--exclude", "--exclude-from",
            "--include", "--strip-components", "--gzip", "--bzip2",
            "--xz", "--zstd", "--lzma", "--lzip", "--lzop", "--compress",
            "--use-compress-program", "--auto-compress", "--verbose",
            "--verify", "--totals", "--checkpoint", "--checkpoint-action",
            "--show-transformed-names", "--transform", "--same-permissions",
            "--preserve-permissions", "--no-same-permissions",
            "--same-owner", "--no-same-owner", "--no-recursion",
            "--recursion", "--one-file-system", "--dereference",
            "--hard-dereference", "--absolute-names", "--keep-old-files",
            "--keep-newer-files", "--overwrite", "--overwrite-dir",
            "--unlink-first", "--mode", "--atime-preserve", "--group",
            "--owner", "--mtime", "--numeric-owner", "--to-stdout",
            "--wildcards", "--no-wildcards", "--anchored", "--no-anchored",
            "--ignore-case", "--no-ignore-case", "--suffix", "--null",
            "--files-from", "--format", "--blocking-factor", "--record-size",
            "--check-device", "--no-check-device",
        ],
    },
    "gzip": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--stdout", "--decompress", "--force", "--help", "--keep",
            "--list", "--license", "--no-name", "--name", "--quiet",
            "--recursive", "--suffix", "--synchronous", "--test",
            "--verbose", "--version", "--fast", "--best", "--rsyncable",
        ],
    },
    "gunzip": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--stdout", "--force", "--help", "--keep", "--list", "--license",
            "--no-name", "--name", "--quiet", "--recursive", "--suffix",
            "--synchronous", "--test", "--verbose", "--version",
        ],
    },
    "unzip": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--help", "--version",
            # unzip's primary interface is single-dash options (-l, -o, -d).
        ],
    },
    "zip": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--help", "--version",
            # zip's primary interface is single-dash options (-r, -q, -9).
        ],
    },
    "rsync": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": [
            "--verbose", "--quiet", "--no-motd", "--checksum", "--archive",
            "--recursive", "--relative", "--no-implied-dirs", "--backup",
            "--backup-dir", "--suffix", "--update", "--inplace", "--append",
            "--append-verify", "--dirs", "--links", "--copy-links",
            "--copy-unsafe-links", "--safe-links", "--munge-links",
            "--copy-dirlinks", "--keep-dirlinks", "--hard-links", "--perms",
            "--executability", "--chmod", "--acls", "--xattrs", "--owner",
            "--group", "--devices", "--specials", "--times", "--atimes",
            "--crtimes", "--omit-dir-times", "--omit-link-times", "--super",
            "--fake-super", "--sparse", "--preallocate", "--dry-run",
            "--whole-file", "--no-whole-file", "--checksum-choice",
            "--one-file-system", "--block-size", "--rsh", "--rsync-path",
            "--existing", "--ignore-existing", "--remove-source-files",
            "--delete", "--delete-before", "--delete-during", "--delete-delay",
            "--delete-after", "--delete-excluded", "--ignore-errors",
            "--force", "--max-delete", "--max-size", "--min-size",
            "--partial", "--partial-dir", "--delay-updates", "--prune-empty-dirs",
            "--numeric-ids", "--usermap", "--groupmap", "--timeout",
            "--contimeout", "--ignore-times", "--size-only", "--modify-window",
            "--temp-dir", "--fuzzy", "--compare-dest", "--copy-dest",
            "--link-dest", "--compress", "--compress-choice",
            "--compress-level", "--skip-compress", "--cvs-exclude",
            "--filter", "--exclude", "--exclude-from", "--include",
            "--include-from", "--files-from", "--from0", "--protect-args",
            "--copy-as", "--address", "--port", "--sockopts",
            "--blocking-io", "--stats", "--8-bit-output", "--human-readable",
            "--progress", "--itemize-changes", "--log-file", "--log-file-format",
            "--password-file", "--early-input", "--list-only", "--bwlimit",
            "--stop-after", "--stop-at", "--fsync", "--write-batch",
            "--only-write-batch", "--read-batch", "--protocol",
            "--iconv", "--checksum-seed",
        ],
    },
    "ssh-keygen": {
        "minPositional": 0, "maxPositional": 50,
        "allowedValueFlags": ["--help", "--version"],
    },
}

# ---------------------------------------------------------------------------
# God-mode operator tools — systemctl, journalctl, ollama, bash, sh.
# These let Cody manage services, inspect logs, and run local LLMs without
# falling back to ask/on-miss.
# ---------------------------------------------------------------------------
GOD_MODE_PROFILES = {
    "systemctl": {
        "minPositional": 0,
        "maxPositional": 10,
        "allowedValueFlags": [
            "--no-pager", "--lines", "--user", "--system", "--quiet",
            "--failed", "--all", "--full", "--plain", "--type",
            "--state", "--output", "--runtime", "--force", "--now",
        ],
    },
    "journalctl": {
        "minPositional": 0,
        "maxPositional": 10,
        "allowedValueFlags": [
            "--unit", "--lines", "--no-pager", "--follow", "--since",
            "--until", "--output", "--reverse", "--grep", "--identifier",
            "--boot", "--catalog", "--priority", "--facility",
            "--system", "--user", "--quiet", "--utc",
        ],
    },
    "ollama": {
        "minPositional": 0,
        "maxPositional": 10,
        "allowedValueFlags": [
            "--model", "--format", "--verbose", "--nowordwrap",
            "--insecure", "--timeout",
        ],
    },
    "bash": {
        "minPositional": 0,
        "maxPositional": 10,
        "allowedValueFlags": [
            "--login", "--noprofile", "--norc", "--posix",
            "--restricted", "--verbose", "--version",
        ],
    },
    "sh": {
        "minPositional": 0,
        "maxPositional": 10,
        "allowedValueFlags": [],
    },
}


def build_exec_config(
    *,
    path_prepend: list[str],
    include_root_admin: bool = False,
    ask: str = "on-miss",
) -> dict:
    """Assemble the tools.exec config block.

    Keeps security=allowlist and ask=on-miss semantics intact:
    anything not listed still prompts the operator via the approval channel
    rather than silently failing or silently running.
    """
    profiles = deepcopy(SAFE_BIN_PROFILES)
    profiles.update(deepcopy(SHELL_UTILITY_PROFILES))
    profiles.update(deepcopy(DEV_TOOL_PROFILES))
    profiles.update(deepcopy(FS_WRITE_PROFILES))
    profiles.update(deepcopy(NETWORK_FETCH_PROFILES))
    profiles.update(deepcopy(AWS_PROFILES))
    profiles.update(deepcopy(AUDIO_MEDIA_PROFILES))
    profiles.update(deepcopy(ARCHIVE_TRANSPORT_PROFILES))
    profiles.update(deepcopy(GOD_MODE_PROFILES))
    if include_root_admin:
        profiles.update(deepcopy(ROOT_ONLY_SAFE_BIN_PROFILES))
    return {
        "security": "allowlist",
        "ask": ask,
        "safeBins": list(profiles.keys()),
        "safeBinProfiles": profiles,
        "pathPrepend": path_prepend,
    }
