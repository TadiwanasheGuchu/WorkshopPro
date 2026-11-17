# WorkshopPro staff guide

Short, task-based guides for workshop staff. Read the page for your role; everyone should
read **Basics** below.

| Role | Guide |
|---|---|
| Service advisor / reception | [Reception](reception.md) |
| Mechanic / technician | [Mechanics](mechanics.md) |
| Workshop manager | [Workshop manager](manager.md) |
| Inventory manager | [Parts and purchasing](parts-and-purchasing.md) |
| Accounts / cashier | [Invoices and payments](accounts.md) |
| Owner / administrator | [Administration](admin.md) |

Rolling WorkshopPro out at a new workshop: [Onboarding plan](onboarding.md).

## Basics

**Signing in.** Open the workshop's WorkshopPro address and sign in with your email and
password. Forgotten password: **Forgot your password?** on the sign-in page sends a reset
link that works once and expires. New staff receive an invitation email and choose their
own password with **Activate your account**.

**What you see depends on your role.** The menu only shows what your role allows, and the
system checks every action again on the server. If you need something you cannot see,
ask the owner or manager to change your role; do not share sign-ins. Each action is
recorded in the audit log under your name.

**Branches.** If you work at more than one branch, choose the branch at the top of the
menu. Lists and new records follow that choice.

**Phones and tablets.** Every screen works on a phone. Mechanics will mostly use job
cards and inspections on a phone; reception and accounts usually use a computer.

**Signing out.** Use the account menu (your initials, top right). Sign out on shared
computers.

## The life of a job

Every vehicle repair runs through one **job card**. Its status tells everyone what is
happening and who acts next.

| Status | Meaning | Usually acts next |
|---|---|---|
| Vehicle received | Vehicle is on site, job card open | Reception / manager |
| Inspection pending | Intake inspection to be done | Mechanic |
| Diagnosis in progress | Finding the fault | Mechanic |
| Awaiting quotation approval | Quotation sent; waiting for the customer | Reception |
| Awaiting parts | Approved, waiting for parts | Parts / manager |
| Repair in progress | Work under way | Mechanic |
| Quality inspection | Work done; being checked | Manager / senior mechanic |
| Ready for collection | Customer can collect | Reception / accounts |
| Completed / collected | Vehicle handed over | — |
| Cancelled | Job stopped (reason recorded) | — |

Status colours: grey = not started or closed, blue = being worked on, yellow = waiting,
green = done or approved, red = overdue, failed or rejected.

**The approval rule.** Work the customer pays for does not start until the customer has
approved the exact quotation version, or a manager records an **authorised exception**
(for example a verbal approval, warranty work or a safety emergency) with the reason. The
system will not let a job move to **Start repair** otherwise.

**Money is never edited.** Issued invoices cannot be changed; corrections are made with a
credit note. Payments cannot be edited or deleted; a mistake is reversed and recorded
again. This keeps the books trustworthy.
