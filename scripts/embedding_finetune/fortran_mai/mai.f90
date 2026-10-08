!=======================================================================
! mai.f90 -- "EmotionManager translated back to 1957"
!
!   A FORTRAN rewrite of MaiBot's emotion core.
!   Source of truth: src/maisaka/agent/emotion.py (2026)
!
!   Formulas (copied verbatim):
!     decay:   e = base + (e - base) * exp(-rate * dt)      [toward baseline]
!     trigger: e = clamp(e + delta, 0, 100)
!
!   tick = 1 hour.  Event schedule duplicated verbatim in compare.py.
!   整活守则: 数值必须和 Python 版逐位对上（容差 1e-9）。
!=======================================================================
program mai_emotion
  implicit none
  integer, parameter :: NEMO = 7, NTICK = 120
  real(8) :: emo(NEMO), base(NEMO), decay_rate
  integer :: tick

  ! 1=happy 2=sad 3=anxious 4=angry 5=calm 6=excited 7=lonely
  ! baseline defaults from emotion.py / AgentConfig (2026)
  base = (/ 40.0d0, 10.0d0, 10.0d0, 8.0d0, 45.0d0, 30.0d0, 15.0d0 /)
  emo  = base
  decay_rate = 0.12d0          ! per hour

  do tick = 1, NTICK
     call apply_decay(emo, base, decay_rate)
     call inject_event(emo, tick)
     call report(tick, emo)
  end do

  write (*,'(A)') '#END'

contains

  !-- decay toward baseline, one hour per tick ---------------------------
  subroutine apply_decay(e, b, rate)
    real(8), intent(inout) :: e(:)
    real(8), intent(in)    :: b(:)
    real(8), intent(in)    :: rate
    e = b + (e - b) * exp(-rate * 1.0d0)      ! array one-liner -- the 1957 way
  end subroutine apply_decay

  !-- event table (MUST match compare.py EVENTS exactly) -----------------
  subroutine inject_event(e, tick)
    real(8), intent(inout) :: e(:)
    integer, intent(in)    :: tick
    select case (tick)
    case (5)
       call bump(e, 1, 25.0d0)      ! happy   : praised
    case (8)
       call bump(e, 6, 30.0d0)      ! excited : good news
    case (12)
       call bump(e, 2, 20.0d0)      ! sad     : a memory
    case (15)
       call bump(e, 7, 18.0d0)      ! lonely  : quiet evening
    case (20)
       call bump(e, 5, 15.0d0)      ! calm    : tea time
    case (30)
       call bump(e, 4, 22.0d0)      ! angry   : interrupted
    case (35)
       call bump(e, 1, 10.0d0)      ! happy
    case (50)
       call bump(e, 3, 20.0d0)      ! anxious : deadline
    case (60)
       call bump(e, 6, 25.0d0)      ! excited
    case (70)
       call bump(e, 2, 15.0d0)      ! sad
    case (85)
       call bump(e, 1, 18.0d0)      ! happy
    case (100)
       call bump(e, 7, 12.0d0)      ! lonely
    end select
  end subroutine inject_event

  subroutine bump(e, i, delta)
    real(8), intent(inout) :: e(:)
    integer, intent(in) :: i
    real(8), intent(in) :: delta
    e(i) = max(0.0d0, min(100.0d0, e(i) + delta))
  end subroutine bump

  !-- human log + machine-readable data line -----------------------------
  subroutine report(tick, e)
    integer, intent(in) :: tick
    real(8), intent(in) :: e(:)
    integer :: i, best
    character(len=16) :: name
    best = 1
    do i = 2, NEMO
       if (e(i) > e(best)) best = i
    end do
    call emo_name(best, name)
    write (*,'(A,I3.3,A,A,A,F5.1,A)') '[TICK ', tick, '] 心情: ', trim(name), &
         ' (', e(best), '/100)'
    write (*,'(A,7F22.15)') '#D', (e(i), i=1,NEMO)
  end subroutine report

  subroutine emo_name(i, name)
    integer, intent(in) :: i
    character(len=16), intent(out) :: name
    select case (i)
    case (1)
       name = '开心'
    case (2)
       name = '难过'
    case (3)
       name = '焦虑'
    case (4)
       name = '生气'
    case (5)
       name = '平静'
    case (6)
       name = '兴奋'
    case (7)
       name = '孤独'
    end select
  end subroutine emo_name

end program mai_emotion
