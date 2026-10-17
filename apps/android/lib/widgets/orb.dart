import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../state/chat_controller.dart';

/// Animated assistant orb. Pulses faster while thinking, turns red on error.
class AvenOrb extends StatefulWidget {
  const AvenOrb({super.key, required this.state, this.size = 120});

  final AvenState state;
  final double size;

  @override
  State<AvenOrb> createState() => _AvenOrbState();
}

class _AvenOrbState extends State<AvenOrb> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 2),
  )..repeat();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final speed = switch (widget.state) {
      AvenState.idle => 1.0,
      AvenState.thinking => 3.0,
      AvenState.error => 0.4,
    };
    final (inner, outer) = switch (widget.state) {
      AvenState.error => (const Color(0xFFF87171), const Color(0xFFB91C1C)),
      AvenState.thinking => (const Color(0xFFA78BFA), const Color(0xFF7C3AED)),
      AvenState.idle => (const Color(0xFF22D3EE), const Color(0xFF7C3AED)),
    };
    return Semantics(
      label: 'Aven status: ${widget.state.name}',
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, _) {
          final pulse =
              1.0 + 0.06 * math.sin(_controller.value * 2 * math.pi * speed);
          return SizedBox(
            width: widget.size,
            height: widget.size,
            child: CustomPaint(painter: _OrbPainter(inner, outer, pulse)),
          );
        },
      ),
    );
  }
}

class _OrbPainter extends CustomPainter {
  _OrbPainter(this.inner, this.outer, this.pulse);

  final Color inner;
  final Color outer;
  final double pulse;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.shortestSide * 0.34 * pulse;

    final glow = Paint()
      ..shader = RadialGradient(colors: [
        Color.fromARGB(70, inner.red, inner.green, inner.blue),
        const Color(0x00000000),
      ]).createShader(Rect.fromCircle(center: center, radius: radius * 1.9));
    canvas.drawCircle(center, radius * 1.9, glow);

    final body = Paint()
      ..shader = RadialGradient(
        center: const Alignment(-0.3, -0.3),
        colors: [inner, outer],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, radius, body);
  }

  @override
  bool shouldRepaint(_OrbPainter old) =>
      old.pulse != pulse || old.inner != inner || old.outer != outer;
}
