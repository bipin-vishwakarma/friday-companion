package com.hermes.deskbuddy

import android.animation.ValueAnimator
import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.View
import android.view.animation.LinearInterpolator
import kotlin.math.*

/**
 * Animated orb persona — pure Canvas, no OpenGL required.
 * Runs fine on Adreno 308 / software fallback.
 */
class PersonaView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
    defStyle: Int = 0
) : View(context, attrs, defStyle) {

    // ── Public control ──────────────────────────────────────────────

    var state: PersonaState = PersonaState.CONNECTING
        set(value) {
            if (field == value) return
            field = value
            onStateChanged(value)
        }

    /** 0.0–1.0 mic/speaker amplitude, drives reactive ring */
    var amplitude: Float = 0f

    // ── Drawing resources ───────────────────────────────────────────

    private val paintOrb = Paint(Paint.ANTI_ALIAS_FLAG)
    private val paintRing = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 4f
    }
    private val paintParticle = Paint(Paint.ANTI_ALIAS_FLAG)
    private val paintGlow = Paint(Paint.ANTI_ALIAS_FLAG)

    // Colour palette
    private val colourIdle      = Color.parseColor("#4FC3F7")   // cool blue
    private val colourListening = Color.parseColor("#80CBC4")   // teal
    private val colourThinking  = Color.parseColor("#CE93D8")   // purple
    private val colourExecuting = Color.parseColor("#FFB74D")   // amber
    private val colourSpeaking  = Color.parseColor("#80DEEA")   // cyan
    private val colourSuccess   = Color.parseColor("#A5D6A7")   // green
    private val colourWarning   = Color.parseColor("#FFF176")   // yellow
    private val colourError     = Color.parseColor("#EF9A9A")   // red
    private val colourOffline   = Color.parseColor("#546E7A")   // dark slate

    // ── Animation state ─────────────────────────────────────────────

    private var breathPhase    = 0f   // 0–2π slow breath
    private var rotationAngle  = 0f   // particle orbit
    private var pulsePhase     = 0f   // fast pulse for thinking/speaking
    private var flashAlpha     = 0f   // success/error flash

    private val breathAnimator = ValueAnimator.ofFloat(0f, (2 * PI).toFloat()).apply {
        duration = 4000
        repeatCount = ValueAnimator.INFINITE
        interpolator = LinearInterpolator()
        addUpdateListener { breathPhase = it.animatedValue as Float; invalidate() }
    }

    private val rotationAnimator = ValueAnimator.ofFloat(0f, 360f).apply {
        duration = 2000
        repeatCount = ValueAnimator.INFINITE
        interpolator = LinearInterpolator()
        addUpdateListener { rotationAngle = it.animatedValue as Float }
    }

    private val pulseAnimator = ValueAnimator.ofFloat(0f, (2 * PI).toFloat()).apply {
        duration = 800
        repeatCount = ValueAnimator.INFINITE
        interpolator = LinearInterpolator()
        addUpdateListener { pulsePhase = it.animatedValue as Float }
    }

    // Particles for THINKING state
    private data class Particle(var angle: Float, val radius: Float, val size: Float, val speed: Float)
    private val particles = List(8) { i ->
        Particle(
            angle  = i * 45f,
            radius = 0.55f + (i % 3) * 0.08f,
            size   = 4f + (i % 3) * 2f,
            speed  = 0.8f + (i % 4) * 0.15f
        )
    }

    // ── Init ────────────────────────────────────────────────────────

    init {
        breathAnimator.start()
        setLayerType(LAYER_TYPE_SOFTWARE, null)   // reliable on low-end GPU
    }

    // ── State transitions ───────────────────────────────────────────

    private fun onStateChanged(s: PersonaState) {
        when (s) {
            PersonaState.THINKING, PersonaState.PLANNING,
            PersonaState.EXECUTING -> {
                rotationAnimator.start()
                pulseAnimator.start()
            }
            PersonaState.SPEAKING, PersonaState.LISTENING -> {
                rotationAnimator.cancel()
                pulseAnimator.start()
            }
            else -> {
                rotationAnimator.cancel()
                pulseAnimator.cancel()
            }
        }
        invalidate()
    }

    // ── Draw ────────────────────────────────────────────────────────

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val cx = width / 2f
        val cy = height / 2f
        val maxR = minOf(cx, cy) * 0.72f

        val colour = stateColour()
        val breath = sin(breathPhase).toFloat() * 0.12f   // ±12% size

        // Soft glow behind orb
        val glowR = maxR * (1.4f + breath * 0.5f)
        paintGlow.shader = RadialGradient(
            cx, cy, glowR,
            intArrayOf(Color.argb(60, Color.red(colour), Color.green(colour), Color.blue(colour)), Color.TRANSPARENT),
            null, Shader.TileMode.CLAMP
        )
        canvas.drawCircle(cx, cy, glowR, paintGlow)

        // Reactive ring (amplitude-driven when listening/speaking)
        if (state == PersonaState.LISTENING || state == PersonaState.SPEAKING) {
            val ringR = maxR * (1.15f + amplitude * 0.25f)
            val ringAlpha = (80 + amplitude * 120).toInt().coerceIn(0, 255)
            paintRing.color = Color.argb(ringAlpha, Color.red(colour), Color.green(colour), Color.blue(colour))
            paintRing.strokeWidth = 3f + amplitude * 6f
            canvas.drawCircle(cx, cy, ringR, paintRing)
        }

        // Orbiting particles (THINKING / PLANNING / EXECUTING)
        if (state in listOf(PersonaState.THINKING, PersonaState.PLANNING, PersonaState.EXECUTING)) {
            for (p in particles) {
                val a = Math.toRadians((p.angle + rotationAngle * p.speed).toDouble())
                val pr = maxR * p.radius
                val px = cx + (pr * cos(a)).toFloat()
                val py = cy + (pr * sin(a)).toFloat()
                val alpha = (140 + sin(pulsePhase + p.angle * 0.05).toFloat() * 80).toInt().coerceIn(0, 255)
                paintParticle.color = Color.argb(alpha, Color.red(colour), Color.green(colour), Color.blue(colour))
                canvas.drawCircle(px, py, p.size, paintParticle)
            }
        }

        // Core orb
        val orbR = maxR * (0.72f + breath)
        paintOrb.shader = RadialGradient(
            cx - orbR * 0.25f, cy - orbR * 0.25f, orbR * 1.1f,
            intArrayOf(
                lighten(colour, 0.35f),
                colour,
                darken(colour, 0.35f)
            ),
            floatArrayOf(0f, 0.5f, 1f),
            Shader.TileMode.CLAMP
        )
        canvas.drawCircle(cx, cy, orbR, paintOrb)

        // Pulse ring for THINKING / SPEAKING
        if (state in listOf(PersonaState.THINKING, PersonaState.PLANNING, PersonaState.SPEAKING)) {
            val pulseR = maxR * (0.85f + sin(pulsePhase).toFloat() * 0.18f)
            val pulseAlpha = (60 + sin(pulsePhase).toFloat() * 50).toInt().coerceIn(0, 200)
            paintRing.color = Color.argb(pulseAlpha, Color.red(colour), Color.green(colour), Color.blue(colour))
            paintRing.strokeWidth = 2f
            canvas.drawCircle(cx, cy, pulseR, paintRing)
        }

        // PC_BOOTING: spinning arc
        if (state == PersonaState.PC_BOOTING || state == PersonaState.CONNECTING
            || state == PersonaState.HERMES_STARTING || state == PersonaState.OMNIROUTE_STARTING) {
            val arcR = maxR * 1.25f
            val sweep = RectF(cx - arcR, cy - arcR, cx + arcR, cy + arcR)
            paintRing.color = Color.argb(180, Color.red(colour), Color.green(colour), Color.blue(colour))
            paintRing.strokeWidth = 5f
            canvas.drawArc(sweep, rotationAngle, 120f, false, paintRing)
            if (!rotationAnimator.isRunning) rotationAnimator.start()
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────

    private fun stateColour() = when (state) {
        PersonaState.IDLE             -> colourIdle
        PersonaState.LISTENING        -> colourListening
        PersonaState.THINKING,
        PersonaState.PLANNING         -> colourThinking
        PersonaState.EXECUTING        -> colourExecuting
        PersonaState.SPEAKING         -> colourSpeaking
        PersonaState.SUCCESS          -> colourSuccess
        PersonaState.WARNING          -> colourWarning
        PersonaState.ERROR            -> colourError
        PersonaState.PC_OFFLINE,
        PersonaState.CONNECTING       -> colourOffline
        PersonaState.PC_BOOTING,
        PersonaState.HERMES_STARTING,
        PersonaState.OMNIROUTE_STARTING -> colourExecuting
        PersonaState.UPDATING         -> colourThinking
    }

    private fun lighten(colour: Int, amount: Float): Int {
        val r = (Color.red(colour) + (255 - Color.red(colour)) * amount).toInt().coerceIn(0, 255)
        val g = (Color.green(colour) + (255 - Color.green(colour)) * amount).toInt().coerceIn(0, 255)
        val b = (Color.blue(colour) + (255 - Color.blue(colour)) * amount).toInt().coerceIn(0, 255)
        return Color.rgb(r, g, b)
    }

    private fun darken(colour: Int, amount: Float): Int {
        val r = (Color.red(colour) * (1 - amount)).toInt().coerceIn(0, 255)
        val g = (Color.green(colour) * (1 - amount)).toInt().coerceIn(0, 255)
        val b = (Color.blue(colour) * (1 - amount)).toInt().coerceIn(0, 255)
        return Color.rgb(r, g, b)
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        breathAnimator.cancel()
        rotationAnimator.cancel()
        pulseAnimator.cancel()
    }
}
