!=======================================================================
! exp29_forgetting.f90 -- "用 1957 年的语言验证 2026 年的量子记忆实验"
!
!   FORTRAN rewrite of exp29_quantum_forgetting.py (trading/ 实验线):
!     granular 现状 / quantum 振幅阻尼 / quantum 两能级 (+间隔复习)
!     拟合 Ebbinghaus 参考点（MAE）
!
!   Formulas copied verbatim from the 2026 source (t = day, absolute):
!     granular:  max(floor, s0 * exp(-t / 24))              floor = 0.2
!     ampdamp:   max(floor, s0 * (1 - p)^t)                 p = 0.05
!     2level:    S*exp(-t/tau_s) + L*exp(-t/tau_l)          tau_s=1  tau_l=200
!                S = s0*0.7 ;  L = s0*c0                    c0 = 0.1
!     review:    on review day:  S := s0*0.7 ;  L += s0*0.3 (consolidate)
!
!   Ebbinghaus reference (hours, retention): the 8 points from the source.
!   照抄复刻，不修模型 —— 目标是逐位复现，不是改进。
!=======================================================================
program exp29_forgetting
  implicit none
  integer, parameter :: NDAY = 31
  real(8), parameter :: S0 = 1.0d0
  real(8) :: g(0:NDAY), qa(0:NDAY), q2(0:NDAY)
  real(8) :: nr(0:NDAY), r1(0:NDAY), rs(0:NDAY)
  real(8) :: imp100(0:100), norm100(0:100), g100(0:100)
  real(8) :: mae

  call make_granular(g, S0, NDAY)
  call make_ampdamp(qa, S0, NDAY)
  call make_2level(q2, S0, 0.1d0, NDAY)
  call make_2level_review(nr, S0, 0, NDAY)
  call make_2level_review(r1, S0, 1, NDAY)
  call make_2level_review(rs, S0, 2, NDAY)
  call make_2level(imp100, S0, 0.5d0, 100)
  call make_2level(norm100, S0, 0.1d0, 100)
  call make_granular(g100, S0, 100)

  ! ---- human-readable summary ----
  write (*,'(A)') '=== exp29 量子遗忘曲线 · Fortran 版（2026 实验 / 1957 语言）==='
  write (*,'(A,F6.2,A,F6.2,A)') '31 天留存 · 两能级 ', q2(31)*100.0d0, &
       '%  vs  granular 现状 ', g(31)*100.0d0, '%'
  write (*,'(A,F6.2,A)') '间隔复习(1/3/7/14) 31 天留存: ', rs(31)*100.0d0, '%'

  ! ---- machine-readable values (#N label value) ----
  mae = fit_mae(g)
  call emit('mae_granular', mae)
  mae = fit_mae(qa)
  call emit('mae_ampdamp', mae)
  mae = fit_mae(q2)
  call emit('mae_2level', mae)

  call emit('g_d1', g(1))
  call emit('g_d2', g(2))
  call emit('g_d6', g(6))
  call emit('g_d31', g(31))
  call emit('qa_d1', qa(1))
  call emit('qa_d2', qa(2))
  call emit('qa_d6', qa(6))
  call emit('qa_d31', qa(31))
  call emit('q2_d1', q2(1))
  call emit('q2_d2', q2(2))
  call emit('q2_d6', q2(6))
  call emit('q2_d31', q2(31))

  call emit('nr_d7', nr(7))
  call emit('nr_d31', nr(31))
  call emit('r1_d7', r1(7))
  call emit('r1_d31', r1(31))
  call emit('rs_d7', rs(7))
  call emit('rs_d31', rs(31))

  call emit('imp100', imp100(100))
  call emit('norm100', norm100(100))
  call emit('g100', g100(100))

  write (*,'(A)') '#END'

contains

  !-- granular: pure exponential + floor (status quo) ---------------------
  subroutine make_granular(c, s0, nd)
    real(8), intent(out) :: c(0:)
    real(8), intent(in)  :: s0
    integer, intent(in)  :: nd
    integer :: t
    do t = 0, nd
       c(t) = max(0.2d0, s0 * exp(-real(t, 8) / 24.0d0))
    end do
  end subroutine make_granular

  !-- quantum amplitude damping: (1-p)^t ----------------------------------
  subroutine make_ampdamp(c, s0, nd)
    real(8), intent(out) :: c(0:)
    real(8), intent(in)  :: s0
    integer, intent(in)  :: nd
    integer :: t
    do t = 0, nd
       c(t) = max(0.2d0, s0 * (1.0d0 - 0.05d0) ** t)
    end do
  end subroutine make_ampdamp

  !-- quantum two-level: S (fast) + L (slow) ------------------------------
  subroutine make_2level(c, s0, c0, nd)
    real(8), intent(out) :: c(0:)
    real(8), intent(in)  :: s0, c0
    integer, intent(in)  :: nd
    integer :: t
    real(8) :: s_, l_
    s_ = s0 * 0.7d0
    l_ = s0 * c0
    do t = 0, nd
       c(t) = s_ * exp(-real(t, 8) / 1.0d0) + l_ * exp(-real(t, 8) / 200.0d0)
    end do
  end subroutine make_2level

  !-- two-level + spaced review ------------------------------------------
  !   mode 0 = no review ; 1 = review on day 1 ; 2 = review on days 1/3/7/14
  !   (S and L updated on review days; decay uses ABSOLUTE t - as in source)
  subroutine make_2level_review(c, s0, mode, nd)
    real(8), intent(out) :: c(0:)
    real(8), intent(in)  :: s0
    integer, intent(in)  :: mode, nd
    integer :: t
    real(8) :: s_, l_
    s_ = s0 * 0.7d0
    l_ = s0 * 0.1d0
    do t = 0, nd
       if (mode == 1 .and. t == 1) then
          s_ = s0 * 0.7d0
          l_ = l_ + s0 * 0.3d0
       end if
       if (mode == 2) then
          if (t == 1 .or. t == 3 .or. t == 7 .or. t == 14) then
             s_ = s0 * 0.7d0
             l_ = l_ + s0 * 0.3d0
          end if
       end if
       c(t) = s_ * exp(-real(t, 8) / 1.0d0) + l_ * exp(-real(t, 8) / 200.0d0)
    end do
  end subroutine make_2level_review

  !-- MAE against the 8 Ebbinghaus reference points (linear interp) -------
  function fit_mae(c) result(mae)
    real(8), intent(in) :: c(0:)
    real(8) :: mae, day, frac, v
    real(8), parameter :: eh(8) = (/ 0.0d0, 0.33d0, 1.0d0, 9.0d0, &
                                     24.0d0, 48.0d0, 144.0d0, 744.0d0 /)
    real(8), parameter :: er(8) = (/ 1.00d0, 0.58d0, 0.44d0, 0.36d0, &
                                     0.33d0, 0.28d0, 0.25d0, 0.21d0 /)
    integer :: k, i0, i1
    mae = 0.0d0
    do k = 1, 8
       day = eh(k) / 24.0d0
       i0 = int(day)
       i1 = min(i0 + 1, NDAY)
       frac = day - real(i0, 8)
       v = c(i0) * (1.0d0 - frac) + c(i1) * frac
       mae = mae + abs(v - er(k))
    end do
    mae = mae / 8.0d0
  end function fit_mae

  !-- one machine-readable line -------------------------------------------
  subroutine emit(label, v)
    character(len=*), intent(in) :: label
    real(8), intent(in) :: v
    write (*,'(A,F22.15)') '#N '//label, v
  end subroutine emit

end program exp29_forgetting
