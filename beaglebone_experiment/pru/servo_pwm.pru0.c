/*
 * Table Tot BBB experiment: PRU0 two-channel servo PWM.
 *
 * P9_31 = PRU0 __R30 bit 0 (head)
 * P9_29 = PRU0 __R30 bit 1 (body)
 *
 * Linux writes the two pulse widths into PRU shared RAM.  No Linux timing is
 * involved in the resulting 20 ms PWM frame.
 */

#include <stdint.h>
#include <pru_cfg.h>
#include "resource_table_empty.h"

volatile register uint32_t __R30;

#define HEAD_BIT             (1u << 0)
#define BODY_BIT             (1u << 1)
#define OUTPUT_BITS          (HEAD_BIT | BODY_BIT)
#define SHARED_RAM           ((volatile uint32_t *)0x00010000)
#define MAGIC                0x544F5431u /* "TOT1" */
#define MAGIC_WORD           0u
#define HEAD_PULSE_WORD      1u
#define BODY_PULSE_WORD      2u
#define FRAME_US             20000u
#define MIN_PULSE_US         500u
#define MAX_PULSE_US         2500u
#define DELAY_BODY_CYCLES    197u

/* __delay_cycles requires a compile-time constant.  The PRU loop/branch adds
 * the remaining few cycles per iteration.  Servo control tolerates this small
 * fixed calibration error; verify pulse widths with a scope before widening
 * mechanical limits. */
static void delay_microseconds(uint32_t microseconds)
{
    while (microseconds-- != 0u) {
        __delay_cycles(DELAY_BODY_CYCLES);
    }
}

static uint32_t clamp_pulse(uint32_t pulse_us)
{
    if (pulse_us < MIN_PULSE_US) return MIN_PULSE_US;
    if (pulse_us > MAX_PULSE_US) return MAX_PULSE_US;
    return pulse_us;
}

int main(void)
{
    volatile uint32_t *shared = SHARED_RAM;
    uint32_t head_us;
    uint32_t body_us;
    uint32_t longest_us;

    /* Enable the PRU OCP master port before accessing shared RAM. */
    CT_CFG.SYSCFG_bit.STANDBY_INIT = 0;
    __R30 = 0;

    while (1) {
        if (shared[MAGIC_WORD] == MAGIC) {
            head_us = clamp_pulse(shared[HEAD_PULSE_WORD]);
            body_us = clamp_pulse(shared[BODY_PULSE_WORD]);
        } else {
            /* Safe neutral until the Linux bridge has initialized RAM. */
            head_us = 1500u;
            body_us = 1500u;
        }

        __R30 |= OUTPUT_BITS;
        if (head_us < body_us) {
            delay_microseconds(head_us);
            __R30 &= ~HEAD_BIT;
            delay_microseconds(body_us - head_us);
            __R30 &= ~BODY_BIT;
            longest_us = body_us;
        } else if (body_us < head_us) {
            delay_microseconds(body_us);
            __R30 &= ~BODY_BIT;
            delay_microseconds(head_us - body_us);
            __R30 &= ~HEAD_BIT;
            longest_us = head_us;
        } else {
            delay_microseconds(head_us);
            __R30 &= ~OUTPUT_BITS;
            longest_us = head_us;
        }
        delay_microseconds(FRAME_US - longest_us);
    }
}
