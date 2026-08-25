# Frame Transport Specification, v1

This document defines four terms and uses each of them exactly twice, because a
specification that varies its terminology is a specification nobody can implement.

## Definitions

A **settled frame** is a frame the receiver has acknowledged and will not request again.
A **provisional frame** is a frame that has been sent but not acknowledged. A **quiet
window** is an interval in which the sender transmits nothing. A **replay boundary** is
the offset from which a reconnecting receiver asks the sender to begin again.

## Sender behaviour

The sender retains every provisional frame until it becomes a settled frame or the
connection closes. It opens a quiet window after every eight frames so that a slow
receiver can catch up, and a second quiet window before it closes. On reconnection the sender reads the replay boundary supplied by
the receiver and resumes from that offset, discarding nothing before it.

## Receiver behaviour

The receiver acknowledges frames in order. An acknowledgement moves the frame to settled
frame state and advances the replay boundary by one. A receiver that observes a quiet
window longer than the configured timeout closes the connection and reconnects.
