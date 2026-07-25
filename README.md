# QLever-eval

This repository provides self-documenting and easy-to-use command-line tools
for setting up and evaluating graph databases in a uniform way. It brings the
workflow of the
[qlever-control](https://github.com/ad-freiburg/qlever-control) project (used
to configure, index, start, query, and benchmark
[QLever](https://github.com/ad-freiburg/qlever)) to other graph databases, so
that competing systems can be set up and evaluated with the same commands and
the same configuration style.

Each supported database is selected as an engine argument to `qeval` (for
example, `qeval oxigraph`) and mirrors the `qeval qlever` command-line
interface. All of them speak
[RDF](https://www.w3.org/TR/rdf11-concepts/) and
[SPARQL](https://www.w3.org/TR/sparql11-overview/), and all of them are driven
by the same `Qleverfile` configuration format. This makes it straightforward to
run the same dataset and the same queries against multiple engines and compare
their behavior and performance.

This project is developed by the QLever team.

# Documentation

The commands share the interface and configuration conventions of QLever. For
the underlying concepts, see the QLever documentation at
<https://docs.qlever.dev/quickstart>.

[//]: # (# Installation)

[//]: # ()
[//]: # (Install the command-line tools as a python package. Using `uv`:)

[//]: # ()
[//]: # (```bash)

[//]: # (uv tool install qlever-eval)

[//]: # (```)

[//]: # ()
[//]: # (Using `pipx`:)

[//]: # ()
[//]: # (```bash)

[//]: # (pipx install qlever-eval)

[//]: # (```)

[//]: # ()
[//]: # (Using `pip`:)

[//]: # ()
[//]: # (```bash)

[//]: # (pip install qlever-eval)

[//]: # (```)

Each supported database can run either inside a container or as a natively
installed engine:

- **Container:** the recommended default. You don't have to install the engine
  yourself; the tool pulls and runs the appropriate image for you. This is
  convenient but comes with a small performance penalty.
- **Native:** you install the engine's binaries yourself, and the tool then
  handles setup, indexing, querying, and evaluation. This avoids the container
  overhead. The exact native installation steps for each engine can be found in
  the GitHub Actions workflows in this repository.

# Use with your own dataset

To evaluate a database on your own dataset, you need a `Qleverfile`. The easiest
way to write one is to get an existing one (using `<command> setup-config ...`)
and change it according to your needs. Pick one for a dataset that is similar to
yours. A [reference of all options](https://docs.qlever.dev/qleverfile/) is
available. The same `Qleverfile` works across the supported databases, so you
can index and query each of them with the same configuration.

# For developers

The (Python) code lives in the `src/` directory. The shared command
infrastructure is in `src/qlever`, and each supported database has its own
package (for example, `src/oxigraph`) that adapts it to that engine.

To make changes or add support for a new database:

```bash
git clone https://github.com/ad-freiburg/qlever-eval
cd qlever-eval
pip install -e ".[dev]"
```

Then you can use the commands just as if you had installed them via `pip`. You
don't have to rerun `pip install -e ".[dev]"` when you modify the `*.py` files,
since the executable created by `pip` links to the files in your working copy.

If you have bug fixes or new useful features, please open a pull request. If you
have questions or suggestions, please open an issue. Files have to be formatted
and linted with `ruff`:

```bash
# manually
ruff format
ruff check
# runs automatically before every commit
pre-commit install
```
