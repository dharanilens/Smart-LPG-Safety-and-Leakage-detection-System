import javax.swing.*;
import javax.swing.table.DefaultTableModel;
import java.awt.*;
import java.awt.geom.AffineTransform;
import java.awt.geom.Path2D;
import java.awt.geom.RoundRectangle2D;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Smart LPG Safety and Leak Detection System - Java (Swing) dashboard.
 * Java port of the Streamlit + Python dashboard: same layout, thresholds,
 * status logic, simulation, charts, history table and CSV download.
 *
 * Compile:  javac LpgDashboard.java
 * Run:      java LpgDashboard        (Java 17 or newer, no external libraries)
 */
public class LpgDashboard {

    // Example raw ADC thresholds only - not calibrated gas concentrations.
    static final int WARNING_THRESHOLD = 1000;
    static final int CRITICAL_THRESHOLD = 1500;
    static final int MAX_READINGS = 100;

    enum Status {
        NORMAL, WARNING, CRITICAL;
        static Status of(int value) {
            if (value >= CRITICAL_THRESHOLD) return CRITICAL;
            if (value >= WARNING_THRESHOLD) return WARNING;
            return NORMAL;
        }
    }

    record Reading(String time, int value, Status status, String source) { }

    // ---------- Streamlit-like palette ----------
    static final Color INK = new Color(0x31333F);
    static final Color MUTED = new Color(0x6B6F7B);
    static final Color SIDEBAR = new Color(0xF0F2F6);
    static final Color RULE = new Color(0xE6E9EF);
    static final Color CHART = new Color(0xFF4B4B);
    static final Color GRID = new Color(0xE6E9EF);

    static final Color OK_BG = new Color(0xE3F5E8), OK_FG = new Color(0x1E4D2B);
    static final Color WARN_BG = new Color(0xFFF8D6), WARN_FG = new Color(0x926C05);
    static final Color ERR_BG = new Color(0xFFE6E6), ERR_FG = new Color(0x7D353B);
    static final Color INFO_BG = new Color(0xE3F0FC), INFO_FG = new Color(0x0F4C81);

    static Font font(int style, float size) { return new Font("SansSerif", style, 1).deriveFont(style, size); }

    /** Coloured rounded message box (st.success / st.warning / st.error / st.info). */
    static class Alert extends JPanel {
        private final JLabel label = new JLabel();
        Alert(String text, Color bg, Color fg) {
            super(new BorderLayout());
            setOpaque(false);
            setBorder(BorderFactory.createEmptyBorder(14, 16, 14, 16));
            label.setFont(font(Font.PLAIN, 15f));
            add(label, BorderLayout.CENTER);
            set(text, bg, fg);
        }
        private Color bg = Color.WHITE;
        void set(String text, Color bg, Color fg) {
            this.bg = bg;
            label.setText(text);
            label.setForeground(fg);
            repaint();
        }
        @Override protected void paintComponent(Graphics g0) {
            Graphics2D g = (Graphics2D) g0.create();
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g.setColor(bg);
            g.fill(new RoundRectangle2D.Float(0, 0, getWidth(), getHeight(), 10, 10));
            g.dispose();
            super.paintComponent(g0);
        }
    }

    static JLabel heading(String text, float size) {
        JLabel l = new JLabel(text);
        l.setFont(font(Font.BOLD, size));
        l.setForeground(INK);
        l.setAlignmentX(Component.LEFT_ALIGNMENT);
        return l;
    }

    static JComponent divider() {
        JSeparator s = new JSeparator();
        s.setForeground(RULE);
        s.setAlignmentX(Component.LEFT_ALIGNMENT);
        s.setMaximumSize(new Dimension(Integer.MAX_VALUE, 1));
        return s;
    }

    static Component gap(int h) { return Box.createRigidArea(new Dimension(0, h)); }

    /** Round "nice" upper bound and step for an axis (1, 2, 5 x 10^k). */
    static double[] niceScale(double max, int ticks) {
        if (max <= 0) max = 1;
        double raw = max / ticks;
        double mag = Math.pow(10, Math.floor(Math.log10(raw)));
        double n = raw / mag;
        double step = (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag;
        return new double[]{Math.ceil(max / step) * step, step};
    }

    // ======================= Charts =======================

    /** st.line_chart equivalent: raw value against reading number. */
    static class LineChart extends JPanel {
        private List<Integer> data = new ArrayList<>();
        LineChart() { setBackground(Color.WHITE); setPreferredSize(new Dimension(600, 300)); }
        void setData(List<Integer> d) { data = d; repaint(); }

        @Override protected void paintComponent(Graphics g0) {
            super.paintComponent(g0);
            Graphics2D g = (Graphics2D) g0.create();
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
            int w = getWidth(), h = getHeight();
            int px = 64, py = 12, pw = w - px - 16, ph = h - py - 52;
            int n = data.size();
            int max = 0;
            for (int v : data) max = Math.max(max, v);
            double[] sc = niceScale(max, 5);
            double yMax = sc[0], step = sc[1];

            g.setFont(font(Font.PLAIN, 12f));
            FontMetrics fm = g.getFontMetrics();
            for (double v = 0; v <= yMax + 1e-9; v += step) {
                int y = (int) Math.round(py + ph - v / yMax * ph);
                g.setColor(GRID);
                g.drawLine(px, y, px + pw, y);
                g.setColor(MUTED);
                String s = String.valueOf((long) v);
                g.drawString(s, px - 8 - fm.stringWidth(s), y + 4);
            }
            // x ticks (reading numbers 1..n)
            int every = Math.max(1, (int) Math.ceil(n / 10.0));
            for (int i = 1; i <= n; i++) {
                if ((i - 1) % every != 0 && i != n) continue;
                double x = xOf(i, n, px, pw);
                g.setColor(MUTED);
                String s = String.valueOf(i);
                g.drawString(s, (int) x - fm.stringWidth(s) / 2, py + ph + 16);
            }
            g.setColor(MUTED);
            g.setFont(font(Font.PLAIN, 12f));
            String xl = "Reading number";
            g.drawString(xl, px + pw / 2 - fm.stringWidth(xl) / 2, h - 10);
            AffineTransform old = g.getTransform();
            g.rotate(-Math.PI / 2, 16, py + ph / 2.0);
            String yl = "Raw ADC value";
            g.drawString(yl, 16 - fm.stringWidth(yl) / 2, py + ph / 2 + 4);
            g.setTransform(old);

            if (n > 0) {
                Path2D path = new Path2D.Double();
                for (int i = 1; i <= n; i++) {
                    double x = xOf(i, n, px, pw), y = py + ph - data.get(i - 1) / yMax * ph;
                    if (i == 1) path.moveTo(x, y); else path.lineTo(x, y);
                }
                g.setColor(CHART);
                g.setStroke(new BasicStroke(2f, BasicStroke.CAP_ROUND, BasicStroke.JOIN_ROUND));
                g.draw(path);
                if (n <= 30) {
                    for (int i = 1; i <= n; i++) {
                        double x = xOf(i, n, px, pw), y = py + ph - data.get(i - 1) / yMax * ph;
                        g.fill(new java.awt.geom.Ellipse2D.Double(x - 3, y - 3, 6, 6));
                    }
                }
            }
            g.dispose();
        }

        private static double xOf(int i, int n, int px, int pw) {
            return n == 1 ? px + pw / 2.0 : px + pw * (i - 1) / (double) (n - 1);
        }
    }

    /** st.bar_chart equivalent: count of readings per status. */
    static class BarChart extends JPanel {
        private final String[] cats = {"NORMAL", "WARNING", "CRITICAL"};
        private int[] counts = new int[3];
        BarChart() { setBackground(Color.WHITE); setPreferredSize(new Dimension(300, 300)); }
        void setCounts(int[] c) { counts = c; repaint(); }

        @Override protected void paintComponent(Graphics g0) {
            super.paintComponent(g0);
            Graphics2D g = (Graphics2D) g0.create();
            g.setRenderingHint(RenderingHints.KEY_ANTIALIASING, RenderingHints.VALUE_ANTIALIAS_ON);
            g.setRenderingHint(RenderingHints.KEY_TEXT_ANTIALIASING, RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
            int w = getWidth(), h = getHeight();
            int px = 40, py = 12, pw = w - px - 12, ph = h - py - 34;
            int max = 0;
            for (int c : counts) max = Math.max(max, c);
            double[] sc = niceScale(Math.max(max, 1), 5);
            double yMax = sc[0], step = Math.max(1, sc[1]);
            g.setFont(font(Font.PLAIN, 12f));
            FontMetrics fm = g.getFontMetrics();
            for (double v = 0; v <= yMax + 1e-9; v += step) {
                int y = (int) Math.round(py + ph - v / yMax * ph);
                g.setColor(GRID);
                g.drawLine(px, y, px + pw, y);
                g.setColor(MUTED);
                String s = String.valueOf((long) v);
                g.drawString(s, px - 8 - fm.stringWidth(s), y + 4);
            }
            double slot = pw / 3.0, bw = slot * 0.62;
            for (int i = 0; i < 3; i++) {
                double x = px + slot * i + (slot - bw) / 2;
                double bh = counts[i] / yMax * ph;
                g.setColor(CHART);
                g.fill(new java.awt.geom.Rectangle2D.Double(x, py + ph - bh, bw, bh));
                g.setColor(MUTED);
                g.drawString(cats[i], (int) (px + slot * i + slot / 2 - fm.stringWidth(cats[i]) / 2.0), py + ph + 18);
            }
            g.dispose();
        }
    }

    /** Realistic raw-ADC leak profile: idle -> leak builds up -> gas clears -> repeat. */
    static class LeakCycle {
        private final Random rnd = new Random();
        private int phase = 0, idleTicks = 0, value = 500;
        int next() {
            switch (phase) {
                case 0 -> {                                   // idle, safe air
                    value = 300 + rnd.nextInt(600);
                    if (++idleTicks >= 6) phase = 1;
                }
                case 1 -> {                                   // leak builds up
                    value += 250 + rnd.nextInt(250);
                    if (value >= 2800) phase = 2;
                }
                default -> {                                  // ventilated, gas clears
                    value -= 300 + rnd.nextInt(250);
                    if (value <= 700) { phase = 0; idleTicks = 0; value = 500; }
                }
            }
            return Math.max(0, value);
        }
    }

    // ======================= Dashboard =======================

    static class Dashboard extends JPanel {
        private static final DateTimeFormatter TS = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        private final Random random = new Random();

        // session state
        private final List<Reading> readings = new ArrayList<>(); // index 0 = newest
        private int currentValue = 500;
        private int simulationCount = 0;

        // live simulation
        private final LeakCycle leakCycle = new LeakCycle();
        private final Timer liveTimer = new Timer(1000, e -> liveTick());
        private final JButton liveBtn = new JButton();
        private final JComboBox<String> liveMode = new JComboBox<>(new String[]{"Leak cycle (idle \u2192 leak \u2192 clear)", "Random readings"});
        private final JComboBox<String> liveSpeed = new JComboBox<>(new String[]{"0.5 s", "1 s", "2 s", "5 s"});
        private final JLabel liveStatus = new JLabel(" ");

        // widgets
        private final JSpinner manualValue = new JSpinner(new SpinnerNumberModel(500, 0, 100000, 100));
        private final Alert banner = new Alert(" ", OK_BG, OK_FG);
        private final JLabel mValue = new JLabel(), mStatus = new JLabel();
        private final LineChart lineChart = new LineChart();
        private final BarChart barChart = new BarChart();
        private final JLabel total = new JLabel();
        private final Alert noChart = new Alert("No readings yet. Generate a simulation reading to begin.", INFO_BG, INFO_FG);
        private final JPanel leftHolder = new JPanel(new CardLayout());
        private final JPanel barHolder = new JPanel(new CardLayout());
        private final JPanel historyHolder = new JPanel(new CardLayout());
        private final DefaultTableModel model =
            new DefaultTableModel(new String[]{"Time", "Raw Sensor Value", "Status", "Source"}, 0) {
                @Override public boolean isCellEditable(int r, int c) { return false; }
                @Override public Class<?> getColumnClass(int c) { return c == 1 ? Integer.class : String.class; }
            };
        private final JLabel footer = new JLabel();

        Dashboard() {
            super(new BorderLayout());
            setBackground(Color.WHITE);
            add(buildSidebar(), BorderLayout.WEST);
            JScrollPane sp = new JScrollPane(buildMain());
            sp.setBorder(BorderFactory.createEmptyBorder());
            sp.getVerticalScrollBar().setUnitIncrement(18);
            add(sp, BorderLayout.CENTER);
            refresh();
        }

        // ---------- sidebar ----------

        private JPanel buildSidebar() {
            JPanel s = new JPanel();
            s.setLayout(new BoxLayout(s, BoxLayout.Y_AXIS));
            s.setBackground(SIDEBAR);
            s.setBorder(BorderFactory.createEmptyBorder(28, 20, 20, 20));
            s.setPreferredSize(new Dimension(280, 0));

            s.add(heading("Dashboard Controls", 22f));
            s.add(gap(10));
            JLabel hint = new JLabel("<html><body style='width:200px'>Use simulation or enter a test reading.</body></html>");
            hint.setFont(font(Font.PLAIN, 14f));
            hint.setForeground(INK);
            hint.setAlignmentX(Component.LEFT_ALIGNMENT);
            s.add(hint);
            s.add(gap(18));

            JLabel lbl = new JLabel("Enter raw sensor value");
            lbl.setFont(font(Font.PLAIN, 14f));
            lbl.setForeground(INK);
            lbl.setAlignmentX(Component.LEFT_ALIGNMENT);
            s.add(lbl);
            s.add(gap(6));
            manualValue.setAlignmentX(Component.LEFT_ALIGNMENT);
            manualValue.setMaximumSize(new Dimension(Integer.MAX_VALUE, 34));
            manualValue.setFont(font(Font.PLAIN, 14f));
            s.add(manualValue);
            s.add(gap(14));

            s.add(sidebarButton("Submit Test Reading", e -> {
                try { manualValue.commitEdit(); } catch (java.text.ParseException ignored) { }
                addReading(((Number) manualValue.getValue()).intValue(), "Manual test");
            }));
            s.add(gap(8));
            s.add(sidebarButton("Generate Simulation Reading", e -> {
                addReading(simulatedValue(), "Simulation");
                simulationCount++;
            }));
            s.add(gap(8));
            s.add(sidebarButton("Clear History", e -> {
                readings.clear();
                currentValue = 500;
                refresh();
            }));
            s.add(gap(20));
            s.add(divider());
            s.add(gap(16));
            s.add(heading("Live Simulation", 18f));
            s.add(gap(10));
            s.add(smallLabel("Mode"));
            s.add(gap(4));
            styleCombo(liveMode);
            s.add(liveMode);
            s.add(gap(10));
            s.add(smallLabel("Update interval"));
            s.add(gap(4));
            styleCombo(liveSpeed);
            liveSpeed.setSelectedIndex(1);
            liveSpeed.addActionListener(e -> liveTimer.setDelay(liveDelayMs()));
            s.add(liveSpeed);
            s.add(gap(12));
            liveBtn.setText("\u25B6 Start Live Simulation");
            liveBtn.setFont(font(Font.PLAIN, 14f));
            liveBtn.setBackground(Color.WHITE);
            liveBtn.setForeground(INK);
            liveBtn.setFocusPainted(false);
            liveBtn.setAlignmentX(Component.LEFT_ALIGNMENT);
            liveBtn.setMaximumSize(new Dimension(Integer.MAX_VALUE, 40));
            liveBtn.addActionListener(e -> toggleLive());
            s.add(liveBtn);
            s.add(gap(8));
            liveStatus.setFont(font(Font.PLAIN, 13f));
            liveStatus.setAlignmentX(Component.LEFT_ALIGNMENT);
            s.add(liveStatus);
            s.add(Box.createVerticalGlue());
            return s;
        }

        private static JLabel smallLabel(String t) {
            JLabel l = new JLabel(t);
            l.setFont(font(Font.PLAIN, 14f));
            l.setForeground(INK);
            l.setAlignmentX(Component.LEFT_ALIGNMENT);
            return l;
        }

        private static void styleCombo(JComboBox<String> c) {
            c.setFont(font(Font.PLAIN, 13f));
            c.setAlignmentX(Component.LEFT_ALIGNMENT);
            c.setMaximumSize(new Dimension(Integer.MAX_VALUE, 32));
        }

        private int liveDelayMs() {
            return switch (liveSpeed.getSelectedIndex()) { case 0 -> 500; case 2 -> 2000; case 3 -> 5000; default -> 1000; };
        }

        /** Start / stop the live simulation. */
        void toggleLive() {
            if (liveTimer.isRunning()) {
                liveTimer.stop();
                liveBtn.setText("\u25B6 Start Live Simulation");
                liveStatus.setText(" ");
            } else {
                liveTimer.setDelay(liveDelayMs());
                liveTimer.start();
                liveBtn.setText("\u23F9 Stop Live Simulation");
                liveStatus.setText("\u25CF LIVE \u2013 adding readings...");
                liveStatus.setForeground(new Color(0xD64545));
            }
        }

        boolean isLive() { return liveTimer.isRunning(); }

        /** One timer tick: produce the next sensor value and record it. */
        void liveTick() {
            int v = liveMode.getSelectedIndex() == 0 ? leakCycle.next() : simulatedValue();
            addReading(v, "Live simulation");
            simulationCount++;
        }

        private JButton sidebarButton(String text, java.awt.event.ActionListener l) {
            JButton b = new JButton(text);
            b.setFont(font(Font.PLAIN, 14f));
            b.setBackground(Color.WHITE);
            b.setForeground(INK);
            b.setFocusPainted(false);
            b.setAlignmentX(Component.LEFT_ALIGNMENT);
            b.setMaximumSize(new Dimension(Integer.MAX_VALUE, 40));
            b.addActionListener(l);
            return b;
        }

        // ---------- main area ----------

        private JComponent buildMain() {
            JPanel m = new ScrollablePanel();
            m.setLayout(new BoxLayout(m, BoxLayout.Y_AXIS));
            m.setBackground(Color.WHITE);
            m.setBorder(BorderFactory.createEmptyBorder(24, 40, 28, 40));

            m.add(heading("🔥 Smart LPG Safety and Leak Detection System", 32f));
            m.add(gap(8));
            m.add(caption("MQ-6 gas sensor monitoring dashboard | Java Swing"));
            m.add(gap(12));
            m.add(divider());
            m.add(gap(14));

            banner.setAlignmentX(Component.LEFT_ALIGNMENT);
            banner.setMaximumSize(new Dimension(Integer.MAX_VALUE, 52));
            m.add(banner);
            m.add(gap(16));

            JPanel metrics = new JPanel(new GridLayout(1, 4, 16, 0));
            metrics.setOpaque(false);
            metrics.setAlignmentX(Component.LEFT_ALIGNMENT);
            metrics.setMaximumSize(new Dimension(Integer.MAX_VALUE, 80));
            metrics.add(metric("Raw Sensor Value", mValue));
            metrics.add(metric("Current Status", mStatus));
            metrics.add(metric("Warning Threshold", new JLabel(String.valueOf(WARNING_THRESHOLD))));
            metrics.add(metric("Critical Threshold", new JLabel(String.valueOf(CRITICAL_THRESHOLD))));
            m.add(metrics);
            m.add(gap(14));
            m.add(divider());
            m.add(gap(14));

            // chart row: 2 : 1
            leftHolder.setOpaque(false);
            JPanel noChartBox = new JPanel(new BorderLayout());
            noChartBox.setOpaque(false);
            noChartBox.add(noChart, BorderLayout.NORTH);
            leftHolder.add(lineChart, "chart");
            leftHolder.add(noChartBox, "empty");
            JPanel left = column(heading("📈 Sensor Reading Chart", 22f), leftHolder);

            barHolder.setOpaque(false);
            barHolder.add(barChart, "chart");
            barHolder.add(new JPanel() {{ setOpaque(false); }}, "empty");
            total.setFont(font(Font.PLAIN, 15f));
            total.setForeground(INK);
            total.setAlignmentX(Component.LEFT_ALIGNMENT);
            JPanel right = column(heading("📊 Status Summary", 22f), barHolder, total);

            JPanel row = new JPanel(new GridBagLayout());
            row.setOpaque(false);
            row.setAlignmentX(Component.LEFT_ALIGNMENT);
            GridBagConstraints c = new GridBagConstraints();
            c.fill = GridBagConstraints.BOTH;
            c.weightx = 2; c.weighty = 1; c.gridx = 0; c.insets = new Insets(0, 0, 0, 24);
            left.setPreferredSize(new Dimension(600, 360));
            row.add(left, c);
            c.weightx = 1; c.gridx = 1; c.insets = new Insets(0, 0, 0, 0);
            right.setPreferredSize(new Dimension(300, 360));
            row.add(right, c);
            row.setMaximumSize(new Dimension(Integer.MAX_VALUE, 380));
            m.add(row);
            m.add(gap(14));
            m.add(divider());
            m.add(gap(14));

            // history
            m.add(heading("🗒️ Sensor Event History", 22f));
            m.add(gap(10));
            historyHolder.setOpaque(false);
            historyHolder.setAlignmentX(Component.LEFT_ALIGNMENT);
            historyHolder.setMaximumSize(new Dimension(Integer.MAX_VALUE, 360));
            JTable table = new JTable(model);
            table.setRowHeight(28);
            table.setFont(font(Font.PLAIN, 13f));
            table.getTableHeader().setFont(font(Font.BOLD, 13f));
            table.getTableHeader().setReorderingAllowed(false);
            table.setGridColor(RULE);
            table.setFillsViewportHeight(true);
            table.setAutoCreateRowSorter(true);
            JScrollPane tsp = new JScrollPane(table);
            tsp.setBorder(BorderFactory.createLineBorder(RULE));
            tsp.setPreferredSize(new Dimension(600, 250));
            JButton dl = new JButton("Download Reading History as CSV");
            dl.setFont(font(Font.PLAIN, 14f));
            dl.setFocusPainted(false);
            dl.addActionListener(e -> downloadCsv());
            JPanel dlRow = new JPanel(new FlowLayout(FlowLayout.LEFT, 0, 0));
            dlRow.setOpaque(false);
            dlRow.add(dl);
            JPanel data = new JPanel(new BorderLayout(0, 12));
            data.setOpaque(false);
            data.add(tsp, BorderLayout.CENTER);
            data.add(dlRow, BorderLayout.SOUTH);
            JPanel emptyBox = new JPanel(new BorderLayout());
            emptyBox.setOpaque(false);
            emptyBox.add(new Alert("Reading history will appear here.", INFO_BG, INFO_FG), BorderLayout.NORTH);
            historyHolder.add(data, "data");
            historyHolder.add(emptyBox, "empty");
            m.add(historyHolder);
            m.add(gap(14));
            m.add(divider());
            m.add(gap(12));

            footer.setText("<html><body style='width:760px'>Important: This is a simulation/manual-input dashboard. "
                + "It does not yet receive physical MQ-6 sensor data. Thresholds are example raw ADC counts, "
                + "not calibrated ppm or validated safety limits. Do not use this app as the sole safety alarm.</body></html>");
            footer.setFont(font(Font.PLAIN, 12f));
            footer.setForeground(MUTED);
            footer.setAlignmentX(Component.LEFT_ALIGNMENT);
            m.add(footer);
            return m;
        }

        private static JLabel caption(String t) {
            JLabel l = new JLabel(t);
            l.setFont(font(Font.PLAIN, 13f));
            l.setForeground(MUTED);
            l.setAlignmentX(Component.LEFT_ALIGNMENT);
            return l;
        }

        private static JPanel column(JComponent title, JComponent... rest) {
            JPanel p = new JPanel();
            p.setLayout(new BoxLayout(p, BoxLayout.Y_AXIS));
            p.setOpaque(false);
            title.setAlignmentX(Component.LEFT_ALIGNMENT);
            p.add(title);
            p.add(gap(10));
            for (JComponent c : rest) { c.setAlignmentX(Component.LEFT_ALIGNMENT); p.add(c); p.add(gap(6)); }
            return p;
        }

        private static JPanel metric(String label, JLabel value) {
            JPanel p = new JPanel();
            p.setLayout(new BoxLayout(p, BoxLayout.Y_AXIS));
            p.setOpaque(false);
            JLabel l = new JLabel(label);
            l.setFont(font(Font.PLAIN, 14f));
            l.setForeground(INK);
            value.setFont(font(Font.PLAIN, 34f));
            value.setForeground(INK);
            l.setAlignmentX(Component.LEFT_ALIGNMENT);
            value.setAlignmentX(Component.LEFT_ALIGNMENT);
            p.add(l);
            p.add(value);
            return p;
        }

        // ---------- behaviour (mirrors the Python functions) ----------

        /** random.choice of four randint ranges, as in the Python app. */
        int simulatedValue() {
            return switch (random.nextInt(4)) {
                case 0 -> randint(100, 900);
                case 1 -> randint(400, 1100);
                case 2 -> randint(1200, 1900);
                default -> randint(2200, 3000);
            };
        }

        private int randint(int lo, int hi) { return lo + random.nextInt(hi - lo + 1); }

        void addReading(int value, String source) {
            readings.add(0, new Reading(LocalDateTime.now().format(TS), value, Status.of(value), source));
            while (readings.size() > MAX_READINGS) readings.remove(readings.size() - 1);
            currentValue = value;
            refresh();
        }

        List<Reading> readings() { return readings; }

        void refresh() {
            Status st = Status.of(currentValue);
            switch (st) {
                case CRITICAL -> banner.set("🚨 CRITICAL STATUS — High demo sensor reading", ERR_BG, ERR_FG);
                case WARNING -> banner.set("⚠️ WARNING STATUS — Elevated demo sensor reading", WARN_BG, WARN_FG);
                default -> banner.set("✅ NORMAL STATUS — Demo reading is below warning threshold", OK_BG, OK_FG);
            }
            mValue.setText(String.valueOf(currentValue));
            mStatus.setText(st.name());

            boolean any = !readings.isEmpty();
            ((CardLayout) leftHolder.getLayout()).show(leftHolder, any ? "chart" : "empty");
            ((CardLayout) barHolder.getLayout()).show(barHolder, any ? "chart" : "empty");
            ((CardLayout) historyHolder.getLayout()).show(historyHolder, any ? "data" : "empty");
            total.setText("Total readings: " + readings.size());

            List<Integer> series = new ArrayList<>();
            int[] counts = new int[3];
            for (int i = readings.size() - 1; i >= 0; i--) series.add(readings.get(i).value());
            for (Reading r : readings) counts[r.status().ordinal()]++;
            lineChart.setData(series);
            barChart.setCounts(counts);

            model.setRowCount(0);
            for (Reading r : readings) model.addRow(new Object[]{r.time(), r.value(), r.status().name(), r.source()});
            revalidate();
            repaint();
        }

        String csv() {
            StringBuilder sb = new StringBuilder("Time,Raw Sensor Value,Status,Source\n");
            for (Reading r : readings)
                sb.append(r.time()).append(',').append(r.value()).append(',').append(r.status()).append(',')
                  .append(r.source()).append('\n');
            return sb.toString();
        }

        private void downloadCsv() {
            JFileChooser fc = new JFileChooser();
            fc.setSelectedFile(new File("lpg_sensor_history.csv"));
            if (fc.showSaveDialog(this) == JFileChooser.APPROVE_OPTION) {
                try {
                    Files.writeString(fc.getSelectedFile().toPath(), csv(), StandardCharsets.UTF_8);
                } catch (IOException ex) {
                    JOptionPane.showMessageDialog(this, "Could not save file: " + ex.getMessage(),
                        "Download failed", JOptionPane.ERROR_MESSAGE);
                }
            }
        }
    }

    /** Panel that follows the viewport width so the page scrolls only vertically. */
    static class ScrollablePanel extends JPanel implements Scrollable {
        public Dimension getPreferredScrollableViewportSize() { return getPreferredSize(); }
        public int getScrollableUnitIncrement(Rectangle r, int o, int d) { return 18; }
        public int getScrollableBlockIncrement(Rectangle r, int o, int d) { return 100; }
        public boolean getScrollableTracksViewportWidth() { return true; }
        public boolean getScrollableTracksViewportHeight() { return false; }
    }

    // ======================= Entry point =======================

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            try { UIManager.setLookAndFeel(UIManager.getSystemLookAndFeelClassName()); } catch (Exception ignored) { }
            JFrame f = new JFrame("Smart LPG Safety Dashboard");
            f.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            f.setContentPane(new Dashboard());
            f.setSize(1280, 900);
            f.setMinimumSize(new Dimension(980, 600));
            f.setLocationRelativeTo(null);
            f.setVisible(true);
        });
    }
}