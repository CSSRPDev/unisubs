Development Workflow
====================

This guide describes the development workflow for Amara.

.. contents::

Creating issues
---------------

Please follow these guidelines when creating issues, to ensure that they are
easy to implement:

  - Do a quick search to check for any existing issues before creating a new
    one.
  - Make sure the title clearly and succinctly captures the issue at hand
  - For bugs, describe the steps needed to reproduce the problem and what
    the correct behavior is.
  - Try to describe the severity of the issue.  Who is it affecting?  How bad
    is the current behavior, etc.

Branches / Repositories
-----------------------

The ``production`` branch is what gets deployed to our production server.
It's what gets deployed to production server.  ``staging`` branch
is what gets deployed to the staging server.

Commits should *never* be made directly to production and only trivial commits
should be made to staging.  Instead, Amara development tries to follow a "one
branch per feature or bugfix" workflow (See :ref:`Workflow <workflow>`)

As you work on your topic branch, other branches may have been merged into
``staging`` by other people.  Make sure you merge staging back to your branch
as often as possible to keep it up-to-date.

Other Git Repositories
----------------------

Inside the unisubs repository, you may want to check out some other repositories.

If you have access to our private repository
(https://github.com/pculture/amara-enterprise/).  Check that out inside the
root directory of the unisubs repository to add the extra functionality.  See
:ref:`optional-apps` for details on how this works.

We also have a couple other repositories that integrate into unisubs:

  - https://github.com/pculture/babelsubs/
  - https://github.com/pculture/unilangs/

Both of these get installed inside your docker container.  Normally you don't
need to do anything to use them.  However, if you want to test changes to
those repositories you need to check out a local copy:

  - Check out the git repository inside the root unisubs directory.
  - Make a symlink from the root directory to the python package (for example:
    ``ln -s babelsubs-git/babelsubs .``)
  - After this the unisubs code will be using your local checkout rather than
    the default package.  Make changes there, test them on your dev
    environment, then commit/push the changes back to a branch on the pculture
    repository, then open a PR to maste.
  - When we deploy amara, we pick up the the latest commit in master for these
    libraries.  So once your changes are merged to master, they will be live
    the next time we deploy.

Testing
-------

At a minimum, make sure you :ref:`run the tests <running-tests>`
after your changes and ensure that all tests pass.

If possible, use test driven development.  Write new tests that cover the
issue you're working on before you start any code.  Write code that makes the
test pass.  Then consider refactoring code to fix the problem in a cleaner
way.

Exception Logging
-----------------

When catching exceptions, be sure to log these with a descriptive message
and the stacktrace. Exceptions should be caught whenever it's necessary
for flow control, an exception is expected, or where user input may cause
unexpected behavior (such as forms).

As an example, here is a function that logs exceptions:

::

    def foo(a, b):
        try:
            do_something(a, b)
        except ValueError:
            logger.error("Invalid input type in Class.foo()", exc_info=True)
        except Exception:
            logger.error("General exception in foo()", exc_info=True)

.. _workflow:

Workflow
--------

We use zenhub for project management.  It's basically a chrome extension that
adds a kanban-like board to github.  You can get it from
https://www.zenhub.com/.

Zenhub adds a pipeline field to github issues.  We use this field to track the
current status of work on the issue.  We use the following pipelines:

  - ``Icebox`` -- Issues that have been deprioritized, or are inside an Epic to be scheduled later
  - ``Discovery`` -- Issues that need to be triaged further and/or prioritized
  - ``Waiting for Design`` -- Issues that need design decisions, mockups, or css before back-end implementation
  - ``To Do`` -- Scheduled issues that a developer hasn't started yet
  - ``In Progress`` -- Issues that a developer is currently working on
  - ``Testing`` -- Issue that a developer believes to be handled and needs
    testing to verify the fix
  - ``Waiting for Deploy`` -- Issue that has been fixed in the staging branch
    and we need to deploy the change to production

Here's the workflow for a typical issue:

  - **Prep work**

    - Someone creates a github issue that captures the bug/feature and puts it
      in the ``Discovery`` pipeline
    - The issue is prioritized and scheduled into a sprint
    - Developer reviews issue Friday before the sprint begins, adds story points
      to the issue

  - **Initial development**

    - A developer creates topic branches for both the ``unisubs`` and
      ``amara-enterprise`` repositories to handle the issue.  The branches
      should be named after its repository and issue number (e.g.
      ``gh-enterprise-1234`` or ``gh-unisubs-5678`` would be branches for
      github issue 1234 in the amara-enterprise repo and github issue 5678 in
      the unisubs repo, respectively).  Changes for the issue get commited to
      these branches.
    - Once development on the issue is complete, developer moves the issue
      to the ``Testing`` pipeline and adds any relevant notes for testing to
      the issue.

  - **Testing**

    - Tester tests the changes.
    - If there are problems, tester notes them on the issue and moves it back to ``In progress``.
    - Developer fixes the problems, adds a note to the issue, moves it back to ``Testing``, and we start testing again
    - Finally, tester approves the changes, then hands it back to developer to do a pull request

  - **Review**

    - Developer merges any new code from staging/master back into the topic branches
    - Developer creates a pull request for unisubs and/or amara-enterprise
      depending on which repositories were changed for the issue
    - A second developer reviews the code
    - If there are issues, the developer #2 adds comments to the PR and works
      with developer #1 to resolve them
    - Once developer #2 thinks the code is ready, they merge the PR
    - Once we decide that staging is ready to be deployed to production, we will
      merge the staging branch to production then deploy andnd moves the issue
      to the ``Waiting for deploy`` pipeline

  - **Deploy**
    - At some point we will deploy the code.
    - Usually this happens on a monday.
    - We first deploy staging, do a check to see if things are okay, then deploy production
    - Once production is deployed, tester closes all issues in ``Waiting for deploy``

