!=======================================================================
! spread.f90 -- A_memorix 扩散激活内核（"Spreading Activation, 1957 style"）
!
!   FORTRAN (C-ABI) rewrite of the spreading-activation BFS core from:
!     src/A_memorix/core/connectionist/spreading_activation.py  (2026)
!
!   Verbatim semantics of the 2026 source:
!     DECAY_COEFFICIENT = 0.85 ;  seeds -> activation = 1.0
!     per frontier node (cur >= min_w), every adjacent edge (BIDIRECTED):
!        spread = cur * edge_weight * 0.85 * recency_factor * (0.3 + 0.7*detail)
!        keep the max activation per node; strict improvement re-queues.
!     `depth` rounds (association_depth).
!
!   Exported via ISO_C_BINDING as `spread_recall` (ctypes-ready).
!   Node ids are 1-based (Fortran native) -- Python side must pass 1-based.
!
!   NOTE (found while building the comparison): the 2026 source updates
!   `activated` IN-PLACE within a round, so its result depends on Python
!   set-iteration order -- an asynchronous-update artifact.  This rewrite
!   uses a SYNCHRONOUS per-round snapshot (the standard, order-independent
!   semantics).  See NOTES.md, third entry.
!
!   NOTE 2 (crash found & fixed while wiring ctypes): in Fortran, a
!   dummy argument WITHOUT `value` is passed BY REFERENCE even under
!   bind(c) -- i.e. an `integer(c_int) :: n` shows up on the C side as
!   `int *n`.  The first ctypes call declared plain `ctypes.c_int` and
!   gfortran dereferenced the integer VALUE as a pointer -> access
!   violation reading 0x3 (=n).  Scalars below carry `value`; array
!   dummies stay by-reference (that is the C "pointer" convention).
!=======================================================================
module spread_mod
  use iso_c_binding
  implicit none
  real(c_double), parameter :: DECAY = 0.85d0
contains

  subroutine spread_recall(n, ne, esrc, edst, ew, erec, edet, nseed, seeds, &
                           depth, minw, act) bind(c, name="spread_recall")
    integer(c_int), value, intent(in)  :: n, ne, nseed, depth
    real(c_double), value, intent(in)  :: minw
    integer(c_int), intent(in)  :: esrc(ne), edst(ne), seeds(nseed)
    real(c_double), intent(in)  :: ew(ne), erec(ne), edet(ne)
    real(c_double), intent(out) :: act(n)

    logical :: in_frontier(n), next_frontier(n)
    integer :: d, e, i, nb
    real(c_double) :: cur, spread
    real(c_double) :: snap(n)      ! per-round snapshot (synchronous semantics)

    act = 0.0d0
    in_frontier = .false.
    do i = 1, nseed
       act(seeds(i)) = 1.0d0
       in_frontier(seeds(i)) = .true.
    end do

    do d = 1, depth
       next_frontier = .false.
       snap = act                  ! synchronous update: read from snapshot
       do i = 1, n
          if (.not. in_frontier(i)) cycle
          cur = snap(i)
          if (cur < minw) cycle
          do e = 1, ne
             if (esrc(e) == i) then
                nb = edst(e)
             else if (edst(e) == i) then
                nb = esrc(e)
             else
                cycle
             end if
             spread = cur * ew(e) * DECAY * erec(e) * (0.3d0 + 0.7d0 * edet(e))
             if (spread >= minw .and. spread > act(nb)) then
                act(nb) = spread
                next_frontier(nb) = .true.
             end if
          end do
       end do
       in_frontier = next_frontier
       if (.not. any(in_frontier)) exit
    end do
  end subroutine spread_recall

end module spread_mod
