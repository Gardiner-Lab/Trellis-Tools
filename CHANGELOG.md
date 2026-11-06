# Changelog

Releases of the Gardiner Lab tool suite. Each one pins versions of the tools
that were tested together; see `docker-compose.yml`.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [semantic versioning](https://semver.org/).

## [Unreleased]

## [2.34.3] - 2026-11-06
Fixes the version the backup console reports, reloads the routing on an update, and checks the
Genome Browser; pins lab-suite-portal, lab-suite-backup and lab-suite-genome 2.34.3.

### Fixed
- **The backup console reported the wrong version, and every install ended in a failure that was
  not one.** Its `APP_VERSION` was left at 2.32.0 through 2.33.0, 2.34.0, 2.34.1 and 2.34.2, so
  `scripts/check.sh` compared it with the version the release pins and reported the console as
  needing a pull, although the container was already running the right image. The Genome Browser
  reported 0.1.0 for the same reason. Every service published from this repo now reports the
  version it is published as.
- **Updating a suite did not pick up a change to the routing.** The proxy's configuration and the
  landing page are bind-mounted from the checkout rather than baked into its image, so Compose saw
  nothing changed about the proxy and left it running as it was: after 2.33.0 added `/genome/`,
  every request to the Genome Browser answered 404 until the proxy was restarted by hand, and
  `install.sh` failed its own health wait on the way. An update now reloads the proxy.

### Changed
- `scripts/check.sh` checks the Genome Browser as it checks every other tool: its page sends a
  signed-out visitor to sign in, `/genome` goes on to `/genome/`, and it is healthy on the pinned
  version. None of this was checked before, which is why the 404 above went unnoticed.
- The Genome Browser's tests now run in the suite's checks and before a release. They were in the
  repository but in no workflow, so 2,400 lines of tests over six files never ran. They run as a
  second `pytest` because `genome/app.py` and `backup/app.py` both import as the module `app` and
  one shadows the other in a single collection.

## [2.34.2] - 2026-11-06
Fixes Genome Browser routing and worker startup; pins lab-suite-portal, lab-suite-backup and
lab-suite-genome 2.34.2.

### Fixed
- **The Genome Browser was unreachable through the proxy.** Its `/genome/` location passed the
  `/genome` prefix through to the app, which serves at its root, so every request answered 404. The
  prefix is now stripped before proxying (as for the sign-in and backup services), so `/genome/` and
  the API and health endpoints resolve.
- **The conversion worker could crash on a fresh install.** It queried the job table before the web
  container had created the schema; the worker now creates its data directories and initialises the
  schema itself (idempotently) before recovering, so it no longer depends on container start order.
- **The conversion worker always showed as unhealthy.** It reused the web image's HTTP health probe
  but runs no web server; the probe is now disabled for the worker (restarts still cover crashes).

## [2.34.1] - 2026-11-05
Fixes the Genome Browser containers failing to start; pins lab-suite-portal, lab-suite-backup and
lab-suite-genome 2.34.1.

### Fixed
- **The Genome Browser would not start.** The web container invoked `gunicorn` and the worker invoked
  `python`, but the image provides neither name: Debian ships gunicorn as a module (run with
  `python3 -m gunicorn`) and Python only as `python3`. Both are now invoked correctly, so the
  genome-browser and genome-worker containers come up. (2.34.0 published the image but it could not
  run; this is the first working Genome Browser release.)

## [2.34.0] - 2026-11-05
Publishes the Genome Browser as a prebuilt image; pins lab-suite-portal, lab-suite-backup and
lab-suite-genome 2.34.0.

### Changed
- The Genome Browser now ships as a published multi-architecture image
  (`ghcr.io/gardiner-lab/lab-suite-genome`, amd64 and arm64), pulled and pinned like the other suite
  services, rather than built on each server. `install.sh` pulls it with the rest; a server without
  the published image yet still builds it from `./genome` through the local overlay. The conversion
  toolchain (samtools, bedtools, deepTools and the UCSC utilities) is baked into the image per
  architecture, with the UCSC binaries verified against pinned checksums at build time.

## [2.33.0] - 2026-11-05
Adds the Genome Browser, and pins lab-suite-portal and lab-suite-backup 2.33.0.

### Added
- Genome Browser (new tool, at `/genome/`): load reference genomes, build a library of aligned
  data tracks, and view them in an IGV-style browser. Reference genomes are uploaded as FASTA (up to
  4 GB); tracks are BigWig, BED or GFF, with BAM and wig files converted to BigWig on the server so
  only the coverage summary is kept. A track is accepted only when every chromosome name and
  coordinate matches the reference genome exactly.
- Sharing follows the suite's model: a reference genome defaults to its owner lab's chair group, a
  track to its owner lab, and either can be shared further by a member of the owner lab.
- Export the current view as an SVG figure, or send it straight to the Lab Notebook.
- Tag a track or genome with a plasmid (MoClo/Plasmid Editor) or a seed stock (Seed Bank); a line or
  plant tag feeds that line's or plant's family tree in the Seed Bank.
- Runs as two containers built from `./genome`: the web service and a single conversion worker
  with its own CPU and memory limits, coordinating through a durable on-disk job queue so an
  accepted conversion survives a restart.

## [2.32.0] - 2026-11-05

Pins Lab Stocks 0.20.0, Seed Bank 0.12.0 and Lab Notebook 0.22.0.

### Added
- **A label of the lab's own.** The labels pages offer LabTAG's labels; a roll the lab buys that is not
  among them is now measured once — the tag, the spot or cap beside it, and the gap — and is offered to
  everyone, in both Lab Stocks and the Seed Bank. Anyone signed in may add, change or remove one, from
  the pencil beside the label picker. The suite keeps them (`label_stocks` in its own database), so they
  are the same for everybody rather than kept in one browser.

### Fixed
- **The spreadsheet for DYMO Connect's Import data lost every column after the first**, `Cap1` among
  them: a sticker's lines of text sat in one cell with line breaks inside the quotes, and DYMO Connect
  reads a line break as the end of the row whatever the quotes. Each line of a sticker is now a column
  of its own, and a row is one line of the file.
- **An LWCS label asked DYMO Connect for the wrong template.** Each LWCS label copies the DY4 label of
  its size and took that label's DYMO stock with it, so LWCS-506 asked for a 56 × 94 mm shipping label
  for a 33 mm label. A roll now names no stock unless one has been recorded for it.
- **DYMO Connect read the spreadsheet as one column** on a computer whose programs separate with a
  semicolon rather than a comma, as Dutch, German and French ones do. It is now written with the
  separator this computer uses, and the labels page offers the other one.
- Lab Notebook 0.22.0: **a lab admin's notebook is their own.** Leading a lab opens the notebooks of
  its members, as it should, but it opened the other lab admins' too, each being a member of the lab.
  An administrator of the suite still reads every notebook, and a lab admin who has left is read by
  the lab's remaining ones, so their work is not lost with them.
- Lab Notebook 0.22.0: **the formatting bar was out of reach in a long text section**, sitting above
  the top of the screen once the section had scrolled, so headings and bullets could not be used
  there. It stays in sight while you write.

## [2.31.0] - 2026-11-05

Pins Sequence Editor 0.21.0, MoClo 1.19.1, Lab Notebook 0.21.2, Seed Bank 0.11.1, Lab Stocks 0.19.1.

### Changed
- **The Plasmid Editor is now the Sequence Editor.** It holds linear fragments and sequencing reads as well
  as plasmids, so the old name was too narrow. The landing page, the top bar on every tool, the help and the
  docs all follow the new name, and inside the editor what it holds is called a *sequence* where it was
  called a plasmid.
- The word *plasmid* is kept wherever it still means one: glycerol stocks in Lab Stocks, parts, backbones and
  assembled plasmids in MoClo, the lines in the Seed Bank, and plasmids linked from the Lab Notebook.
- **Nothing moves.** The address is still `/editor/`, the published image is still `plasmid-editor`, the
  container and the database file keep their names, and no record changes. An upgrade needs no migration.

## [2.30.2] - 2026-11-05

Tool versions are unchanged from 2.30.1 (Lab Notebook 0.21.1). The teaching demo
gains a step; nothing in the suite itself changes.

### Added
- **The teaching demo goes on to a knock-out.** `demo/demo.sh load` now also runs the CRISPR Designer:
  two guides on the tRFP reporter (AtU6-26 promoter) become a Level 2 construct with a Cas9 unit in
  position 1 and a kanamycin unit in position 3, which goes into the Plasmid Editor, is kept in
  Agrobacterium in Lab Stocks, and is planned on a notebook page. The kanamycin unit is the kit's own
  NOS:nptII cassette (`demo/data/pICSL70004.gb`, MIT, from the moclo registry). **The Cas9 CDS is not
  Cas9**: a site-free reading frame of the same length, named and described as a stand-in, because no
  Cas9 sequence ships with the suite. The two acceptors it assembles into are minimal stand-ins too.

### Fixed
- `demo/demo.sh` trusts the lab's certificate authority (`certs/lab-suite-ca.crt`) and asks for the
  suite over https when it has its own certificate: with an `http://` address in `SUITE_PUBLIC_URL` it
  only met a redirect and lost the sign-in.

## [2.30.1] - 2026-11-05

Pins Lab Notebook 0.21.1.

### Added
- Lab Notebook 0.21.1: a line begun with "- " becomes a bulleted list as the next character is typed.

### Fixed
- Lab Notebook 0.21.1: the day box beside **Start today** takes the day as dd-mm-yyyy, whatever the browser's
  language; it was the browser's own date box, which often asked for yyyy-mm-dd. A calendar button beside it
  picks a day as before.

## [2.30.0] - 2026-11-04

Pins Lab Stocks 0.19.0.

### Added
- **Which lab each eLab owner belongs to** is now a tab of the dashboard, under Administration: a
  shared eLab group holds several labs' samples, and this says whose stock each becomes when it is
  brought over. Until now the list could only be set through the API.

## [2.29.1] - 2026-11-04

Pins Lab Stocks 0.18.1.

### Fixed
- Lab Stocks 0.18.1: a sample brought over into another lab is linked to the sample it came from -
  without it those came over loose, and the next lab to connect would have copied them into eLab again.
  Everyone who may see a stock now also sees where it is in eLab, rather than only the lab that owns it.

## [2.29.0] - 2026-11-04

Pins Lab Stocks 0.18.0.

### Added
- Lab Stocks 0.18.0: a sample brought over from a shared eLab group becomes the stock of the lab
  whoever made it belongs to, rather than always the lab doing the bringing over. Who belongs where is
  kept and can be set; an owner nobody has placed stays with the connecting lab, credited to the
  administrator.
- Lab Stocks 0.17.0: a kind can be kept in several of eLab's sample types, so a MoClo kit filed under
  its own type comes over as glycerol stocks; and a stock is no longer copied into eLab a second time
  when the group already holds that plasmid under its own name.

## [2.28.0] - 2026-11-04

Pins Lab Notebook 0.21.0 and Lab Stocks 0.16.0.

### Added
- Lab Stocks 0.15.0 and 0.16.0: **sharing stock lists between labs.** A lab's lead or lab admin can share one
  list — glycerol stocks, primers, chemicals, antibodies or plant material — or all of them, with another lab,
  with its own chair group, or with any other chair group, to see or to change; an administrator can turn on
  sharing for a whole chair group, which stacks with per-lab shares. A shared stock still belongs to the lab that
  made it (eLab is still sent by that lab); edits are kept in its history and a delete is a soft delete, so a
  shared lab's changes are recorded and recoverable. **Share stocks…** on each list opens the dialog, for a lab's
  lead, lab admin or an administrator, who is asked which lab if they are in none.
- Lab Notebook 0.21.0: **steps can be moved.** Drag the ⋮⋮ at the left of a step, or press Alt+↑ / Alt+↓ in it;
  a step keeps its tick.
- Lab Notebook 0.21.0: **＋ Add to page…** on a protocol, and in the library, adds it as a page of its own under
  today's day (the first choice) or any page you may add to, instead of more content in the day; its version is
  recorded and listed under the protocol's *Used on*.
- Lab Notebook 0.21.0: **a mistaken year, month or day can be deleted** (a year typed as 6, or 6202), with the
  days under it, and brought back from Deleted. One with a booking on it is kept until the booking is
  cancelled, and a deleted day cannot come back beside a new one for the same date.

### Fixed
- Lab Notebook 0.21.0: the buttons above a page wrap inside it in a narrow window, instead of being squeezed so
  their names broke over two lines.

## [2.27.0] - 2026-11-04

Pins Plasmid Editor 0.20.1.

### Changed
- Four of the Plasmid Editor now run at once rather than one, set with **`EDITOR_WORKERS`** in `.env`
  (default 4; 1 restores the old behaviour). It is the one tool that does real arithmetic in a
  request, and a single worker served one of those at a time while everyone else waited. Measured
  with 20 people at once and a 60 kb plasmid scanned against every REBASE enzyme in the mix:
  ordinary pages went from 3.9 s to 0.5 s at the 95th percentile, and saving from 7.3 s to 1.1 s.
  About 65 MB per worker. The other tools are unchanged: none of them compute in a request.

## [2.26.0] - 2026-11-04

Pins Lab Stocks 0.15.0.

### Added
- Lab Stocks 0.15.0: **sharing stock lists between labs.** A lab's lead or lab admin can share one list —
  glycerol stocks, primers, chemicals, antibodies or plant material — or all of them, with another lab or with
  its own chair group, to see or to change; an administrator can turn on sharing for a whole chair group, which
  stacks with per-lab shares. A shared stock still belongs to the lab that made it (eLab is still sent by that
  lab); edits are kept in its history and a delete is a soft delete, so a shared lab's changes are recorded and
  recoverable. **Share stocks…** on each list opens the dialog, for a lab's lead, lab admin or an administrator.

## [2.25.0] - 2026-10-31

Pins Plasmid Editor 0.20.0.

### Added
- Plasmid Editor 0.20.0: adding a stock by its number now copes with the lab's older numbering. A
  padded number (GL-G-00178) finds the stock (GL-G-0178), and a number from before the suite
  (gGL000179) makes a stock of its own with the next number, keeping the tube's label.

## [2.24.2] - 2026-10-31

Pins Plasmid Editor 0.19.2.

### Added
- Plasmid Editor 0.19.2: a glycerol stock can be added from the editor tab as well, beside the stock
  chips already shown on an open plasmid. That is where a plasmid is looked at, so the second strain's
  stock can be recorded without going to the sequencing page.

## [2.24.1] - 2026-10-31

Pins Plasmid Editor 0.19.1.

### Fixed
- Plasmid Editor 0.19.1: glycerol stocks are listed, and can be added, on every plasmid rather than
  only one confirmed by sequencing here. A lab moving its records over has stocks for plasmids that
  were never confirmed in the suite, and had no way to record them.

## [2.24.0] - 2026-10-31

Pins Plasmid Editor 0.19.0.

### Added
- Plasmid Editor 0.19.0: a plasmid can have more than one glycerol stock, which is how it is normally
  kept - the cloning strain and the strain it was moved into. The editor lists every stock Lab Stocks
  holds for the plasmid, and another can be added at any time: a new one for Lab Stocks to number, or
  one that already has a number, linked to the plasmid so it is listed with the rest.

## [2.23.1] - 2026-10-31

Pins Plasmid Editor 0.18.1.

### Fixed
- Plasmid Editor 0.18.1: dates in the editor are written the European way everywhere (31-10-2026), in
  the reader's own time rather than the server's UTC; three places still showed the raw stamp. The
  chromatogram's call panel also stays put after a base is called.

## [2.23.0] - 2026-10-31

Pins Plasmid Editor 0.18.0.

### Added
- Plasmid Editor 0.18.0: a base can be called by hand from the chromatogram. Where the basecaller
  committed to a letter the peak does not support, whoever reads the trace can say what it shows; the
  read is aligned again, so the mismatch stops being counted. The instrument's own bases are kept, with
  the call laid over them and who made it recorded.

## [2.22.0] - 2026-10-31

Pins Plasmid Editor 0.17.0.

### Added
- Plasmid Editor 0.17.0: sequencing reads can be put into a clone after they are uploaded - several at
  once by ticking them in the map, or one at a time from the read itself. Setting a read's clone no
  longer means judging it: the verdict, and who gave it, are left untouched.

## [2.21.1] - 2026-10-31

Pins Plasmid Editor 0.16.1.

### Added
- Plasmid Editor 0.16.1: the editor's help page now explains how read alignment works - the quality
  trimming, the local affine-gap alignment and its scores, circular origins, large insertions, and what
  makes a read count as mapped - alongside a section on comparing the reads of a clone.

## [2.21.0] - 2026-10-31

Pins Plasmid Editor 0.16.0.

### Added
- Plasmid Editor 0.16.0: the sequencing page compares the reads of a clone against each other. Where
  several reads cover the same base they settle between them whether a difference is the clone's own
  sequence or a bad basecall, so a ragged read end no longer reads as a mutation. Each clone shows what
  its reads confirm, what they contradict, and how much of the plasmid they reached.

## [2.20.2] - 2026-10-31

Pins Plasmid Editor 0.15.1.

### Fixed
- Plasmid Editor 0.15.1: typing in the enzyme filter made every count read as 6, after 0.15.0 changed the
  table to rely on the counts the server sends. Introduced in 2.20.1 and fixed the same day.

## [2.20.1] - 2026-10-31

Pins Plasmid Editor 0.15.0.

### Fixed
- Plasmid Editor 0.15.0: choosing a large enzyme set (**All REBASE**) hung the browser, and on a long
  sequence killed the tab. A 150 kb sequence against all of REBASE now takes under 4 seconds instead of 76,
  and downloads 0.6 MB instead of 55 MB. Past 2,000 sites the sequence is left unmarked, with the enzyme
  table still counting every one; smaller sets behave as before.

## [2.20.0] - 2026-10-31

Pins Lab Notebook 0.20.0, Plasmid Editor 0.14.0, MoClo Library Tool 1.19.0, Booking 0.4.0, Seed Bank 0.11.0
and Lab Stocks 0.14.0.

### Added
- Two pages for the suite itself, linked from the landing page and from each other:
  **How an experiment runs through Trellis Tools** (`/suite/help`) follows one construct from design to a
  homozygous line through every tool — designing and checking it, building and recording it, confirming the
  clone, into plants, growing and scoring, the next generation, a cross with a neighbouring lab, and then
  following the whole thread back — with sections on sharing between people and labs, the habits that keep
  it working, and what is kept where. **About Trellis Tools** (`/suite/about`) says why it exists, what the
  tools are, what holds them together, how sharing works, how it sits alongside eLabJournal, and what happens
  to your data, and both describe the **family tree**: the one page that gathers a record's whole history —
  its construct and glycerol stocks, its parents and the chain of seeds back through every generation,
  everything grown from it since, and the notebook pages about each step — across all the tools at once.
- Neither page assumes whose lab is running the suite: it reads correctly wherever it is deployed, and
  `landing/tools.json` is where a deployment puts its own name in the footer.

## [2.19.1] - 2026-10-31

Pins MoClo Library Tool 1.18.1 and Seed Bank 0.10.1.

### Added
- Seed Bank 0.10.1: an individual plant can be marked **dead** or **discarded**, not only a whole sowing.

### Fixed
- MoClo Library Tool 1.18.1: a cassette card cut off its **SVG** and delete buttons, after a fourth export
  button was added to a row that does not wrap.

## [2.19.0] - 2026-10-30

Pins Lab Notebook 0.19.0, Plasmid Editor 0.13.0, MoClo Library Tool 1.18.0, Booking 0.3.0, Seed Bank 0.10.0
and Lab Stocks 0.13.0.

### Added
- **About** and **How to use** pages for every tool, reached from each one's top bar and from its empty lists:
  what the tool is, what it holds, how it fits with the others and who sees what; then the habits that keep
  its records honest, the steps for each routine job, and how to put mistakes right.
- Lab Notebook 0.19.0: attached documents open in the notebook itself, over the page; a page shows previews of
  the notes under it, as cards.

### Fixed
- Plasmid Editor 0.13.0: searching a sequence that reads on the **reverse strand** marked it on the forward
  strand only; the complement was never highlighted. A hit is now marked on the strand it reads on.
- Plasmid Editor 0.12.0: Gateway **LR** reactions read a circular donor as if it were linear, so an entry clone
  whose file started between its att sites gave a product carrying the entry backbone and ccdB instead of the
  gene. Both products of the crossover are now reported, with the features of both parents.

## [2.18.0] - 2026-10-30

Pins Lab Notebook 0.18.0, Seed Bank 0.9.0, Lab Stocks 0.12.0, Plasmid Editor 0.11.0 and MoClo Library Tool 1.17.0.

### Added
- Lab Notebook 0.18.0: tables paste in from Excel and other spreadsheets (as a table in text, or filling a table
  from a cell); a table's column names are changed in its header; colours for letters, a marker switched on and
  off like a pen (with No highlight), strike-through and three headings in the formatting bar; long steps and
  their title wrap.
- MoClo Library Tool 1.17.0: saved constructs and plasmids on the dashboard link to the plasmid (or cassette)
  itself.

### Changed
- Dates are written day-first in every tool (30-10-2026, 30-10-2026 16:40). Lab Notebook day pages are named
  30-10-2026 Thursday and months October 2026; existing ones are renamed when the notebook starts.
- Dates are written day-first, as in Europe: 30-10-2026, and 30-10-2026 16:40 on the 24-hour clock, on the
  dashboard (accounts, labs, the certificate) and in the backup console (backups and the last run, in local time).

## [2.17.0] - 2026-10-26

Pins Lab Notebook 0.17.0, Seed Bank 0.8.0 and Lab Stocks 0.11.0; adds the file converter (Gotenberg 8.15.3).

### Added
- Attachments open in the browser without downloading: Word, PowerPoint and Excel files (.doc, .docx, .ppt,
  .pptx, .xls, .xlsx, OpenDocument, RTF, CSV) in the Lab Notebook, the Seed Bank and Lab Stocks are shown as PDFs,
  made by a new **file converter** service (LibreOffice, in Gotenberg) the first time each file is opened and kept
  for the next time. Text files (notes, FASTA, GenBank) open as plain text. The original still downloads.
- The converter is on an internal network of its own: only those three tools reach it, and it cannot reach the
  internet, so files never leave the server. `make check` reports its health.

## [2.16.4] - 2026-10-26

Pins Lab Stocks 0.10.0.

### Added
- Lab Stocks 0.10.0: **the lab's own people** in eLab, set by the lab admin in the bring-over dialog. Stocks
  brought over from a shared eLab group are made by their eLab owner when that owner is one of the lab's people,
  and credited to the administrator otherwise, the eLab owner kept and shown as "Owner in eLab".

### Fixed
- Lab Stocks 0.10.0: an eLab sample with no place in its box (position -1) is brought over without one.

## [2.16.3] - 2026-10-26

Pins Lab Stocks 0.9.0.

### Added
- Lab Stocks 0.9.0: **⇧ Update from eLab**, for the lab admin: takes what was changed in eLab since it was last
  sent (a glycerol stock's fields, places in storage, names of those brought over), eLab being right where both
  were changed. Only when pressed.

## [2.16.2] - 2026-10-26

Pins Lab Stocks 0.8.0.

### Fixed
- Lab Stocks 0.8.0: bringing over many glycerol stocks or tubes from eLab could stop part way and leave them
  unlinked, after which every round tried to make them in eLab ("There is no free space at position ...").
  Now they come over 25 at a time, linked as they are made, with a progress bar; a round links one whose
  place in eLab holds an unlinked sample of its name, rather than making it, so those left unlinked mend
  themselves; and bringing over again links what was left instead of making it twice.

### Changed
- Lab Stocks 0.8.0: what is brought over from eLab is made by its owner in eLab; eLab is right, and the
  owners are looked up every hour and corrected here when they differ.

## [2.16.1] - 2026-10-26

Pins Lab Notebook 0.16.1.

### Added
- Lab Notebook 0.16.1: Tab in text works as in a word processor - it puts in a tab (Shift+Tab takes it
  back), and in a list it moves the item in a level (Shift+Tab out). Tabs are kept in the PDF and Word exports.

## [2.16.0] - 2026-10-24

Pins Seed Bank 0.7.0 (where plants grow, phenotypes by treatment, family trees, chair groups), Lab Stocks 0.7.0
and Plasmid Editor 0.10.0 (links to family trees).

### Added
- **A teaching demo** (demo/README.md): `make demo` makes the Demo Chair Group with Demo Lab and Demo Partner Lab,
  the shared accounts `demo` (lab admin) and `demo-partner` (password `trellis-demo`), and fills them through the
  tools' own API with one connected piece of work in every tool: MoClo cassettes and plasmids, the plasmids
  sequenced and confirmed in the editor, glycerol stocks, primers, chemicals, antibodies and orders, a transgenic
  line from dipping to a homozygous T3 with a scored drought trial and a cross with the partner lab, notebook
  pages linking all of it with a protocol and a shared page, and bookings. `make demo-reset` removes only the
  demo's data and loads it again; `make demo-wipe` removes it.
- Shared teaching accounts: their passwords cannot be changed from the dashboard. With DEMO_SHOW_ON_LOGIN=1 the
  sign-in page offers the demo login.

### Changed
- The Seed Bank reads Lab Stocks' database (read-only), for family trees from a plasmid through its glycerol
  stocks to the lines and seeds made with it; the Plasmid Editor gets SEEDS_URL=/seeds, for its link there.

## [2.15.0] - 2026-10-23

Pins MoClo 1.16.0, Plasmid Editor 0.9.0, Lab Notebook 0.16.0, Seed Bank 0.6.0, Lab Stocks 0.6.0 and Lab Booking 0.2.0: Trellis Tools' look in every module.

### Added
- **Trellis Tools' look** (design/trellis.css): one palette - green for what you do, brown for structure, on
  warm paper-white - and one header for every module: Trellis Tools, then the module's icon and name, its
  tabs, the person and Log out. design/sync.sh copies it, with the icons, into each module. The landing
  page, sign-in, registration, the dashboard and the backup console use it; each tool's card on the
  landing page is edged in its own earthy accent (moss olive, teal, ochre, green, slate, plum).
- Small icons for inside the modules, in place of emoji (docs/icon/make_glyphs.py; static/trellis/glyphs/).
- The look's green is a shade darker, and the ochre too, so text on them and them on white read easily
  (WCAG AA); its element rules only fill in what a module leaves unset.
- The dashboard's tabs show glyphs: a tab may name one ("glyph" in a tool's suite-manifest.json; its "icon"
  emoji stays as the fallback). Glyphs are served at /account/glyphs/.
- The backup console in the same look, its two emoji glyphs.

### Changed
- The tools' icons on the landing page are drawn in Trellis Tools' style - brown and green, round lines -
  instead of emoji: DNA parts with sticky ends (MoClo), a plasmid map (Plasmid Editor), a notebook with a
  leaf (Lab Notebook), a sprouting seed (Seed Bank), a tube (Lab Stocks), a ticked calendar (Booking), a
  key (Dashboard) and an archive box (Backups). Served at /account/icons/; drawn by
  docs/icon/make_tool_icons.py. A tool in tools.json names its icon as "image"; "icon" stays as the fallback.

## [2.14.0] - 2026-10-23

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.15.1 |
| Plasmid Editor | 0.8.1 |
| Lab Notebook | 0.15.1 |
| Seed Bank | 0.5.3 |
| Lab Stocks | 0.5.3 |
| Booking | 0.1.2 |
| Sign-in service | 2.14.0 |
| Backup service | 2.14.0 |

### Changed
- **The suite is called Trellis Tools**: the landing page, sign-in, registration, the dashboard and the
  backup console, and the docs. The landing page says it is made by the Gardiner Lab. The repositories,
  images and the lab certificate authority's name are unchanged (a new authority would have to be
  trusted again on every computer).
- **Its icon**: a DNA double helix as a trellis, with a vine climbing it, in brown and green - in the browser tab,
  on the landing page and on the sign-in page (served at /account/trellis.svg; drawn by docs/icon/make_icon.py).

## [2.13.0] - 2026-10-23

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.15.0 |
| Plasmid Editor | 0.8.0 |
| Lab Notebook | 0.15.0 |
| Seed Bank | 0.5.2 |
| Lab Stocks | 0.5.2 |
| Booking | 0.1.1 |
| Sign-in service | 2.13.0 |
| Backup service | 2.13.0 |

### Added
- **Archiving people who leave.** On the dashboard, Archive (Accounts tab for administrators; a lab's
  members for its lab admin, for someone only in labs they run). The account and its labs are kept, so
  all their work stays where it is - notebook, plasmids, stocks, seeds, parts - for their labs' leads
  and lab admins; they no longer sign in (an open session ends at once), are left out of the tools'
  lists of people, and their bookings ahead are freed. Listed under "Left the lab", with Bring back.
  A lab with archived people cannot be removed. Remove still deletes an account, and now says so.

### Fixed
- Lab leads and lab admins saw a stray "null" on the Labs tab.

## [2.12.0] - 2026-10-23

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.15.0 |
| Plasmid Editor | 0.8.0 |
| Lab Notebook | 0.14.0 |
| Seed Bank | 0.5.1 |
| Lab Stocks | 0.5.1 |
| Booking | 0.1.0 |
| Sign-in service | 2.12.0 |
| Backup service | 2.12.0 |

### Added
- **Booking** (lab-booking 0.1.0), at /booking/: rooms and equipment that lab admins add and share with
  labs and chair groups, booked ahead on a week calendar (today highlighted) or by finding a free slot,
  with the people in each booking; on the dashboard, My bookings and Rooms & equipment. Backed up
  nightly with the rest (booking.db).
- The Lab Notebook (0.14.0) shows each day's bookings on the day, reading the Booking tool's volume, and
  gives every booked day a page.

## [2.11.0] - 2026-10-23

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.15.0 |
| Plasmid Editor | 0.8.0 |
| Lab Notebook | 0.13.0 |
| Seed Bank | 0.5.1 |
| Lab Stocks | 0.5.1 |
| Sign-in service | 2.11.0 |
| Backup service | 2.11.0 |

### Added
- **The dashboard's Hosting tab** (administrators), for the suite at an address of its own: the
  public address (label QR codes open it), whether people may register, and whether they need a
  lab's code - set there instead of in .env, at once and for every tool. And a checklist of how the
  suite stands: the certificate the proxy serves for that address (trusted by every browser, or the
  lab's own; for that name; how long it has left), HSTS, sign-in cookies, registration,
  administrators still on the published default password, and the last backup. See docs/HTTPS.md,
  A public address.
- **Password guessing is limited.** The proxy lets one address try to sign in or register at most 10
  times a minute, with a burst of 10; the sign-in service stops an address after 10 wrong passwords
  for one account, for 15 minutes, without locking the account for anyone else.
- **HSTS on the public address**: browsers reaching the suite there are told to use https only.
- Label QR codes in Lab Stocks and the Seed Bank (0.5.1) open the public address set there.

## [2.10.0] - 2026-10-23

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.15.0 |
| Plasmid Editor | 0.8.0 |
| Lab Notebook | 0.13.0 |
| Seed Bank | 0.5.0 |
| Lab Stocks | 0.5.0 |
| Sign-in service | 2.10.0 |
| Backup service | 2.10.0 |

### Added
- More goes into the Lab Notebook (Lab Notebook 0.13.0): from the Plasmid Editor (0.8.0), a plasmid
  map, a cloning product, a PCR, a designed primer pair and a sequencing read; from the MoClo Library
  Tool (1.15.0), a part, a plasmid and a cassette - each with its pictures and what they show, into a
  day's page. MoClo is told where the notebook is (`NOTEBOOK_URL=/notebook`).
- Ladders of your own for the Plasmid Editor's virtual gel, shared with the chair group.
- Labels for the DYMO LabelWriter 550 on LabTAG labels (Lab Stocks 0.5.0, Seed Bank 0.5.0): the labels
  page shows and prints the labels as the LabTAG label chosen, and downloads a zip of .dymo files for
  DYMO Connect. A select-all tick heads each list.

### Changed
- MoClo: a plasmid's export options come first, in one row.

## [2.9.9] - 2026-10-23

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.7.0 |
| Lab Notebook | 0.12.0 |
| Seed Bank | 0.4.1 |
| Lab Stocks | 0.4.3 |
| Sign-in service | 2.9.9 |
| Backup service | 2.9.9 |

### Added
- A virtual digest goes into the Lab Notebook (Plasmid Editor 0.7.0, Lab Notebook 0.12.0): 📓 Add to
  notebook, under the editor's virtual gel, puts the gel and its fragments into a day's page - today's,
  or a day chosen - as a gel photo with its wells numbered and named, and a table of the fragments with
  a column to tick off the bands seen on the real gel. The editor is told where the notebook is
  (`NOTEBOOK_URL=/notebook`).

## [2.9.8] - 2026-10-23

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.6.2 |
| Lab Notebook | 0.11.0 |
| Seed Bank | 0.4.1 |
| Lab Stocks | 0.4.3 |
| Sign-in service | 2.9.8 |
| Backup service | 2.9.8 |

### Added
- Lab Notebook 0.11.0: pages shared to work on together. A lab member shares a page (or a day), and
  everything under it, with people or labs of their chair group; they find it under "Shared with me",
  change it, add pages under it, and can show it under a page of their own as well - one page in both
  notebooks, so a change shows in both. An open page shows others' saves within half a minute.
  Chair groups are set by an administrator on the dashboard; without one, a page is shared within the
  owner's own labs.

## [2.9.7] - 2026-10-23

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.6.2 |
| Lab Notebook | 0.10.2 |
| Seed Bank | 0.4.1 |
| Lab Stocks | 0.4.3 |
| Sign-in service | 2.9.7 |
| Backup service | 2.9.7 |

### Added
- Plasmid Editor 0.6.2: the sequence a read has that the reference doesn't. Each stretch of a read
  that did not align is listed under its alignment, with where it lies and its bases as the plasmid
  reads them, to copy, copy as FASTA or search with NCBI BLAST; one at either end of the alignment
  can be inserted into the reference where the read leaves it. A read that did not align at all
  shows its whole sequence, to BLAST.

## [2.9.6] - 2026-10-22

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.6.1 |
| Lab Notebook | 0.10.2 |
| Seed Bank | 0.4.1 |
| Lab Stocks | 0.4.3 |
| Sign-in service | 2.9.6 |
| Backup service | 2.9.6 |

### Changed
- Plasmid Editor 0.6.1: sequencing alignments can be read at a glance. Every read is drawn on one
  map of the plasmid, under its features, with a mark at each difference (red mismatch, violet
  insertion, orange deletion; hollow on a low-quality call), the parts of it that did not align
  reaching out from its ends, and below them what the reads cover together and which features no
  read covers completely. A read opens with its verdict in a sentence, each difference names its
  feature and the read's quality there, the alignment's rows are labelled with a coloured strip
  showing where read and reference agree, and the chromatogram scrolls to whichever difference or
  base is chosen.
- `docker-compose.local.yml` also builds Seed Bank and Lab Stocks from local checkouts
  (`SEEDS_SRC`, `STOCKS_SRC`), like the other tools.

### Fixed
- Plasmid Editor 0.6.1: a read's identity ignored the bases it has extra or lacks, so a read with a
  60 bp insertion was reported as "100% identity". It now counts them; whether a read maps still
  rests on the bases that pair up. Existing reads show the new figure after **Re-align all**.

## [2.9.5] - 2026-10-22

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.5.5 |
| Lab Notebook | 0.10.2 |
| Seed Bank | 0.4.1 |
| Lab Stocks | 0.4.3 |
| Sign-in service | 2.9.5 |
| Backup service | 2.9.5 |

### Added
- Plasmid Editor 0.5.5: a sequencing read's alignment shows its own "Read extent" - the read's full
  length, trimmed, aligned and unmatched stretches - so a large insertion or a wrong reference is
  visible even when it isn't stitched into the alignment.

### Fixed
- Plasmid Editor 0.5.5: a read with a large, unexpected insertion only showed the flank either side of
  it that aligned better, with the other flank and the insertion itself silently dropped. Both flanks
  are now found and stitched together, with the insertion held in the alignment as read bases the
  reference does not have.

## [2.9.4] - 2026-10-21

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.5.4 |
| Lab Notebook | 0.10.2 |
| Seed Bank | 0.4.1 |
| Lab Stocks | 0.4.3 |
| Sign-in service | 2.9.4 |
| Backup service | 2.9.4 |

### Added
- Seed Bank 0.4.1: seed lots in eLabJournal, as Lab Stocks copies them there. Above the lists, how
  many of the lab's are sent, waiting, archived in eLab or failed, with Send now; on a lot's page,
  its sample in eLab and how it stands, with sending it now or again.

## [2.9.3] - 2026-10-21

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.5.4 |
| Lab Notebook | 0.10.2 |
| Seed Bank | 0.4.0 |
| Lab Stocks | 0.4.3 |
| Sign-in service | 2.9.3 |
| Backup service | 2.9.3 |

### Changed
- Lab Stocks 0.4.3: bringing samples over from eLab, everyone owning samples there stays listed,
  also when all of theirs are here already (greyed, with nothing to tick).

## [2.9.2] - 2026-10-20

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.5.4 |
| Lab Notebook | 0.10.2 |
| Seed Bank | 0.4.0 |
| Lab Stocks | 0.4.2 |
| Sign-in service | 2.9.2 |
| Backup service | 2.9.2 |

### Changed
- Lab Stocks 0.4.2: everyone in a lab sees the lab's orders, and those of the other labs of its chair
  group (marked with their lab); no other lab sees them. Each lab's own lab admins still order them.

## [2.9.1] - 2026-10-20

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.5.4 |
| Lab Notebook | 0.10.2 |
| Seed Bank | 0.4.0 |
| Lab Stocks | 0.4.1 |
| Sign-in service | 2.9.1 |
| Backup service | 2.9.1 |

### Added
- Plasmid Editor 0.5.4: digests are kept as lanes of the virtual gel for each open tab until it is
  closed, so banding patterns can be compared side by side.
- Lab Stocks 0.4.1: a primer's 5′ and 3′ modifications, given on its order as suppliers want them
  (5′-[6-FAM]GTAAAACGACGGCCAGT[BHQ-1]-3′).

### Fixed
- Plasmid Editor 0.5.4: the virtual gel's ladder sizes and lane names are no longer cut off.

## [2.9.0] - 2026-10-20

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.5.3 |
| Lab Notebook | 0.10.2 |
| Seed Bank | 0.4.0 |
| Lab Stocks | 0.4.0 |
| Sign-in service | 2.9.0 |
| Backup service | 2.9.0 |

### Added
- Lab Stocks 0.4.0:
  - **eLabJournal**: a lab admin connects the lab with *Connect to eLabJournal*, which walks them
    through making a token in eLab, tries it, and lets them choose what is copied, to which of the
    group's own sample types (Glycerol Stock, Plant Material, Plant Seed), and the lab's permit and
    biosafety level. Glycerol stocks, plant material and the Seed Bank's seed lots are then copied
    to eLab one way, into the fields those types have (nothing is added to them), and archived
    there when used up or deleted. Nothing is made twice. Each record's page links to its sample in
    eLab and says how it stands; one archived in eLab can be sent again.
  - **Bring over from eLab**: eLab's glycerol stocks and plant material become records here, and
    its seed samples lines and lots in the Seed Bank, each linked to its sample, which keeps its name.
  - **Plant material** (GL-M): tubes kept for later processing, a box of them at once, linked from
    the notebook.
  - Glycerol stocks: biosafety (permit, biosafety level, host system), insert and hazard, plant and
    yeast markers; a storage location chosen from eLab's storage, or added there, with a place in a box.
  - Labs of a chair group see each other's stocks, read-only.
- Seed Bank 0.4.0: a line's biosafety, stock center and genetics (permit, biosafety level, GMO type,
  gene expression, selection marker, mutation information, construction method, stock center
  collection and number, accession, link).
- Lab Notebook 0.10.2: links to Lab Stocks' plant material.
- Chair groups: an administrator makes them and puts labs in them on the dashboard's Labs tab (each
  lab in one at most); lab leads and lab admins see their lab's.
- `.env.example` and `docker-compose.yml`: optional `ELAB_*` settings, for connecting every lab to
  one eLab by hand (usually each lab connects on the stocks page instead).

### Upgrading
- Lab Stocks, the Seed Bank and the sign-in service add their new tables and columns on starting.
- A test copy of the suite connected to the same eLab group as the live one would change the same
  samples: connect each lab from one installation only.

## [2.8.0] - 2026-10-19

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.5.3 |
| Lab Notebook | 0.10.1 |
| Seed Bank | 0.3.0 |
| Lab Stocks | 0.3.0 |
| Sign-in service | 2.8.0 |
| Backup service | 2.8.0 |

### Added
- Lab Stocks 0.3.0:
  - **Chemicals**: name, CAS number (checked), room, size and safety data sheet, with links to
    SOFOS and Chemwatch, and an Out switch for one that has run out.
  - **Antibodies**: the lab's short code, description, primary/secondary/other, producer, source
    animal, product number and notes about the use.
  - **Orders**, the lab's order list. Anyone in a lab sends an order request, or uses 🛒 Add to
    order on a chemical, primer or antibody (primers can be ticked in their list and added at
    once). A chemical switched to Out is added by itself. The lab's **lab admins** see that lab's
    orders only, with the number waiting on the Orders tab, and mark them ordered and received; a
    stock that had run out is then back in stock. The list downloads as a spreadsheet.
- Lab Notebook 0.10.1: chemicals and antibodies can be linked from notes, like other stocks.

### Changed
- Plasmid Editor 0.5.3: designed primers saved to Lab Stocks name their binding sites after their
  codes, and Simulate PCR lists the primers on the sequence (annotated, and the lab's that bind).
- The landing page describes Lab Stocks' chemicals, antibodies and orders.

## [2.7.1] - 2026-10-19

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.14.1 |
| Plasmid Editor | 0.5.2 |
| Lab Notebook | 0.10.0 |
| Seed Bank | 0.3.0 |
| Lab Stocks | 0.2.0 |
| Sign-in service | 2.7.1 |
| Backup service | 2.7.1 |

### Changed
- MoClo Library Tool 1.14.1: plasmid maps are drawn as the Plasmid Editor draws them. A plasmid's
  window shows its map, and it downloads as PNG or SVG.
- Plasmid Editor 0.5.2: a crowded circular map grows to fit, rather than cutting labels off.

### Fixed
- The Checks workflow gives its proxy check a throwaway certificate, since the real one is made on
  the lab's server (it had failed on every push since https came in 2.6.0).

## [2.7.0] - 2026-10-19

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.1 |
| Plasmid Editor | 0.5.0 |
| Lab Notebook | 0.10.0 |
| Seed Bank | 0.3.0 |
| Lab Stocks | 0.2.0 |
| Sign-in service | 2.7.0 |
| Backup service | 2.7.0 |

### Added
- **Lab admin**, a new role: a lab lead who also adds people to the lab (a new account, or an
  existing one) and takes them out of it, on the dashboard's Labs tab. Only administrators delete
  accounts or change roles.
- **People can belong to several labs**, with a role in each (member, lab lead or lab admin).
  Administrators add and remove labs per person, and set the role in each, on the Accounts tab;
  a lab's lab admin adds people to it and takes them out. Registration still joins one lab.
  - Kept in suite.db's new lab_members table; existing memberships are carried over once. The
    members table keeps each person's first lab, for tools that read only one.

- Plasmid Editor 0.5.0: "Cutting at most [N] time(s)" in the Enzymes panel shows only the enzymes
  that cut that many times or fewer (formerly "Unique cutters only").

### Changed
- **Plasmids are always seen by everyone in their owner's labs**, and by other labs only once their
  owner ticks **Public** in the editor (Plasmid Editor 0.5.0). Public is off for every existing
  plasmid, so after upgrading, plasmids that were visible to other labs no longer are until made
  public. The notebook, Seed Bank and Lab Stocks follow the same rule when linking plasmids.
- Lab Notebook 0.10.0, Seed Bank 0.3.0, Lab Stocks 0.2.0: someone in several labs sees all of them;
  in Seed Bank and Lab Stocks a picker at the top chooses which lab new records go to.

### Removed
- The "In the pipeline" section of the landing page, and tools.json's planned list.

## [2.6.2] - 2026-10-16

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.1 |
| Plasmid Editor | 0.4.3 |
| Lab Notebook | 0.9.0 |
| Seed Bank | 0.2.0 |
| Lab Stocks | 0.1.2 |
| Sign-in service | 2.6.2 |
| Backup service | 2.6.2 |

### Changed
- Lab Stocks 0.1.2: a glycerol stock opens its plasmid in the editor with one click (🧬 Open in the
  Plasmid Editor), and can be linked to its plasmid, or to another, afterwards. A stock whose plasmid
  cannot be opened says why.
- Plasmid Editor 0.4.3: the plasmids open in the editor come first in the Sequencing page's
  reference list.

## [2.6.1] - 2026-10-16

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.1 |
| Plasmid Editor | 0.4.2 |
| Lab Notebook | 0.9.0 |
| Seed Bank | 0.2.0 |
| Lab Stocks | 0.1.1 |
| Sign-in service | 2.6.1 |
| Backup service | 2.6.1 |

### Fixed
- Copy buttons work over plain http as well as https, in every tool: the Plasmid Editor 0.4.2
  (sequences, selections, cloning products, lab codes), the MoClo Library Tool 1.13.1 (the admin
  page and the guide designer) and Lab Stocks 0.1.1 (primers), as on the dashboard in 2.6.0.

## [2.6.0] - 2026-10-16

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.4.1 |
| Lab Notebook | 0.9.0 |
| Seed Bank | 0.2.0 |
| Lab Stocks | 0.1.0 |
| Sign-in service | 2.6.0 |
| Backup service | 2.6.0 |

### Added
- **HTTPS.** The suite is served over https on its port, and plain http to it is sent on to https,
  so bookmarks keep working.
  - `install.sh` makes a certificate authority of the lab's own and a certificate for the machine
    (`scripts/make-certs.sh`, `make certs`), and renews the machine's when its names change or it
    nears its end.
  - Each computer trusts the authority once, without administrator rights, from
    `/lab-suite-ca.crt` (no sign-in needed); see docs/HTTPS.md. A university certificate can be
    used instead.
  - Sign-in cookies are secure by default (`SESSION_COOKIE_SECURE=true`).
  - Copy buttons work: browsers allow copying only on secure pages.
- **Lab Stocks** at `/stocks/`, a new tool in the suite: glycerol stocks (`GL-G-0042`) and primers
  (`GL-O-0007`), numbered per lab.
  - Each glycerol stock is linked to its plasmid in the Plasmid Editor.
  - Primers record their sequence, with length, GC and Tm worked out, and can be searched by any
    piece of it.
  - Storage, labels with QR codes, photos and files, and links from the notebook.
  - A lab's stocks are shared within the lab and hidden from other labs.
  - It has its own volume, `stocks-data`. Backups, the backup console and restores include it.

### Changed
- Plasmid Editor 0.4.1: confirming a plasmid by sequencing can make its glycerol stock in Lab
  Stocks, with the lab's next number; a plasmid's stocks show beside its tags; designed primers are
  saved to the lab's primers with one click, and **Lab primers** finds the lab's primers that bind
  a sequence.
- Lab Notebook 0.9.0 (from 0.4.1; see its changelog):
  - links to Lab Stocks with `@`;
  - export to PDF and Word from any level of the tree, with photos, attached PDFs' pages and files;
  - lab leads share notebooks with labs or people, and protocols are their lab's, shared with other
    labs by their authors (existing protocols become their author's lab's);
  - gel photos with numbered wells, numbered photos of plants, and a markup editor for photos.

### Fixed
- The Copy button for a lab's registration code on the dashboard copies over plain http too.

## [2.5.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.4.1 |
| Seed Bank | 0.2.0 |
| Sign-in service | 2.5.0 |
| Backup service | 2.5.0 |

### Changed
- Seed Bank 0.2.0: every code starts with its lab's own code (GL-S-0042), so no two labs' codes are
  ever the same.
  - Each lab numbers from 1.
  - The lab lead or an admin can choose the lab code before the lab's first record.
- Lab Notebook 0.4.1: seed links read the new codes.

## [2.4.1] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.4.0 |
| Seed Bank | 0.1.0 |
| Sign-in service | 2.4.1 |
| Backup service | 2.4.1 |

### Fixed
- **Backups could copy secrets to the backup drive.** The configuration archive took the whole suite
  folder minus a few names (`.env`, `*.key`, `*.pem`). Anything else went along to the backup drive
  in every nightly archive:
  - a copy of `.env` (`.env.bak`, a renamed env file);
  - the `pre-install-backup/` snapshots, with every account's password hash and the labs'
    registration codes;
  - caches.

  It now takes a list of named files: the compose files, `nginx/`, `landing/`, `scripts/`, `docs/`,
  `.env.example`, `Makefile`, `install.sh`. Secret-looking files are left out even inside those
  folders. A test runs the real script against a folder full of such files.
- **`make check` tested the wrong thing.**
  - Signed out, every tool page is answered by the proxy's sign-in redirect, so the checks of
    `/login`, `/parts` and `/editor/login` passed even with MoClo or the editor down.
  - It also ignored `SUITE_PORT` in `.env`, so a suite on another port was never the one checked.

  It now reads the port from `.env` (as text, never running it), checks the sign-in gate for
  what it is, and checks each tool behind the proxy at its health route. It also compares each
  tool's running version with the version this release pins.

## [2.4.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.4.0 |
| Seed Bank | 0.1.0 |
| Sign-in service | 2.4.0 |
| Backup service | 2.4.0 |

### Added
- **Seed Bank** at `/seeds/`, a new tool in the suite: plant lines, seed lots and plants, with
  lineage traced plant by plant.
  - Each line records the plasmids it carries, from the Plasmid Editor.
  - Segregation tests, storage locations, phenotypes with photos and 3D scans.
  - Labels with QR codes, and links from the notebook.
  - A lab's stocks are shared within the lab and hidden from other labs.
  - It has its own volume, `seeds-data`. Backups, the backup console and restores include it.
  - `SUITE_PUBLIC_URL` (e.g. `http://UU115629:8080`) sets where label QR codes point, so phones
    can reach them.

### Changed
- Lab Notebook 0.4.0: link seed lots, plants and lines from the Seed Bank with `@`.

## [2.3.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.3.0 |
| Sign-in service | 2.3.0 |
| Backup service | 2.3.0 |

### Changed
- Lab Notebook 0.3.0: photos and attachments on pages and protocols.
  - Any kind of file can be attached: Word, PowerPoint, Excel, PDF and more.
  - Photos show in the page, PDFs open in the browser, and Office files open in their programs.
  - The files are kept in the notebook's database, so backups include them. The database, and so
    each backup, grows with the photos attached.

## [2.2.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.2.0 |
| Sign-in service | 2.2.0 |
| Backup service | 2.2.0 |

### Changed
- Lab Notebook 0.2.0: a 🗑 Deleted view to bring deleted pages and protocols back. Owners restore
  their own, protocol editors their protocols, and administrators anything.

## [2.1.1] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.1.1 |
| Sign-in service | 2.1.1 |
| Backup service | 2.1.1 |

### Fixed
- **Backups failed after installing 2.1.0.** The backup could not read the Lab Notebook's
  database from its read-only mount, because the notebook kept it in SQLite's WAL mode. A failure
  to copy any one database stops the backup, so nothing was backed up. Lab Notebook 0.1.1 uses the
  ordinary journal, as the other tools do, and converts its database when it starts.

## [2.1.0] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.5 |
| Lab Notebook | 0.1.0 |
| Sign-in service | 2.1.0 |
| Backup service | 2.1.0 |

### Added
- **Lab Notebook** at `/notebook/`, a new tool in the suite: everyone's notebook of days and pages,
  a shared protocol library with active tables, MoClo reactions and plasmid links that open in the
  Plasmid Editor. Its design follows Trilium Notes. Lab leads read their lab's notebooks and
  administrators read all of them. It has its own volume, `notebook-data`, and reads the account
  directory, the editor's plasmids and the labs without changing them.
- Backups, the backup console and restores include the notebook's database.
- `/notebook/health` answers without signing in, like the other tools' health checks.

### Changed
- Plasmid Editor 0.3.5: the "✓ Sequenced" and new "Not sequenced" tags open the plasmid on the
  Sequencing page.

## [2.0.4] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.4 |
| Sign-in service | 2.0.4 |
| Backup service | 2.0.4 |

### Changed
- Plasmid Editor 0.3.4: correct a plasmid to its sequencing read, with
  features and translations moving along; every change to a sequence is kept
  in its history with who made it, and any version can be rolled back to; a
  save over a newer version is held back instead of overwriting it.

## [2.0.3] - 2026-10-15

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.3 |
| Sign-in service | 2.0.3 |
| Backup service | 2.0.3 |

### Changed
- Plasmid Editor 0.3.3: the differences in a sequencing alignment can be
  clicked to go to them, with Previous and Next between them; and judging an
  alignment sufficient needs the glycerol stock the clone is kept as.

## [2.0.2] - 2026-10-14

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.2 |
| Sign-in service | 2.0.2 |
| Backup service | 2.0.2 |

### Changed
- Plasmid Editor 0.3.2: select and copy amino acids on a translation, Find's
  selected match is visible, and the Enzymes panel's Choose… button fits.

### Fixed
- The proxy and the sign-in service reported themselves unhealthy in
  `docker ps` although both worked: their health checks asked `localhost`,
  which in Alpine is the IPv6 address first, where neither listens. They ask
  `127.0.0.1` now.

## [2.0.1] - 2026-10-14

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.1 |
| Sign-in service | 2.0.1 |
| Backup service | 2.0.1 |

### Changed
- Plasmid Editor 0.3.1: the sequences open in the editor are kept, as tabs in
  the Open panel, until signing out (unsaved edits included), keyed by the
  suite's id for the sign-in; and the editor's side panels stay in view while
  the sequence scrolls.

## [2.0.0] - 2026-10-14

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.13.0 |
| Plasmid Editor | 0.3.0 |
| Sign-in service | 2.0.0 |
| Backup service | 2.0.0 |

### Added
- **One sign-in for every tool.** Signing in at `/account/login` signs in to
  MoClo, the Plasmid Editor and the backup console at once, and signing out
  signs out of all of them. A new sign-in service (`lab-suite-portal`) owns the
  session; the proxy asks it who is signed in before each request and tells the
  tool. See "One sign-in" in the README.
- **Nothing is visible before signing in or registering**: the landing page
  and every tool send someone who is not signed in to the sign-in page, and
  back afterwards. Only the tools' health checks stay open.
- **One registration page, one set of lab codes, for every tool**, at
  `/account/register`. Every lab's registration code is generated by the suite,
  and a new lab gets one straight away. Who is in which lab and who leads it
  are kept by the suite, and every tool reads them from there.
- **One dashboard for every control**, at `/account/`: your account and
  password, your MoClo parts and saved constructs, and for administrators the
  labs and their codes, every account (add, remove, set a password, lab and
  role), the MoClo library and backups. Tools add their own tabs through a
  `suite-manifest.json`. The landing page shows who is signed in, with a link to
  it.
- `suite.db`, in a new `suite-data` volume, holds the labs and memberships, and
  is in every backup.
- Each sign-in has its own id, passed to the tools as `X-Suite-Session`, for
  what they keep until signing out (the Plasmid Editor's open tabs).

### Changed
- MoClo's, the editor's and the backup console's own sign-in pages, the
  editor's registration page, MoClo's Dashboard and Admin pages, the editor's
  Admin page and the backup console now send people to the suite's sign-in,
  registration and dashboard.
- Accounts are managed only on the dashboard: MoClo's own user management and
  account settings are switched off inside the suite.
- Changing your password no longer signs you out; it signs out your other
  sessions.
- The labs, codes, memberships and lab leads set on the Plasmid Editor's Admin
  page are brought over when the suite first starts, so codes already handed out
  keep working.
- A new installation starts with the administrator `admin` / `admin123` (set
  `ADMIN_PASSWORD` to start with your own). Signing in with `admin123` opens
  only My account, to choose a new password; no tool, page or administration
  opens until it is changed, and it cannot be chosen again.
- The installer no longer makes up a registration code (`REGISTRATION_CODE`);
  it prints the one the suite generated. `REQUIRE_REGISTRATION_CODE=false` lets
  anyone register without one.
- **Everyone is signed out once** when updating to this release, and signs in
  again on the new page with the same username and password.
- The backup console no longer has a sign-in of its own; an administrator who is
  signed in to the suite goes straight in.
- `docker-compose.local.yml` also builds MoClo from a checkout (`MOCLO_SRC`), and
  the installer does so while a pinned MoClo release is not published yet.

## [1.0.0] - 2026-10-12

First release.

| Component | Version |
| --- | --- |
| MoClo Library Tool | 1.12.0 |
| Plasmid Editor | 0.2.1 |
| Backup service | 1.0.0 |

### Added
- One stack behind one port: a landing page, the MoClo Library Tool at `/`, the
  Plasmid Editor at `/editor/`, and a backup console at `/backup/`, with a
  "Lab tools" link back to the landing page in each tool.
- `install.sh`: one command to install or update. It takes over an existing MoClo
  Library Tool with its users and data (snapshot first, every table checked,
  automatic rollback on failure, `--rollback` afterwards), and replaces MoClo's
  published default admin password.
- One account for every tool, and one registration page for the suite: people
  choose their lab and give that lab's registration code. Labs, codes and the lab
  lead role are managed on the Plasmid Editor's Admin page.
- Nightly verified backups with daily, weekly and monthly retention, to a folder
  or straight to a network drive (SMB), with a console to run, download, upload,
  verify and restore them.

### Fixed
- Redirects from the proxy kept port 80 instead of the suite's port.
- Every backup archive contained all earlier ones, by way of the suite's own
  `backups/` folder in the configuration snapshot.
