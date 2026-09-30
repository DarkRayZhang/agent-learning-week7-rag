package com.laozhang.assistant.tool;

// ══════════════════════════════════════════════════════════════════════
//  ★ 空白页测验 · 第一题：工具类
// ══════════════════════════════════════════════════════════════════════
// 要求（闭卷，别翻 week7/java/ 的代码，别翻聊天记录）：
//
//   写一个 `AssistantTools`，内含**一个** `@Tool` 方法：
//
//       addReminder(String content, String time)
//
//   三条硬要求：
//     ① 返回值必须是 **`Map`**（不是 `String`）
//        —— 想清楚：为什么返回 String 是"不确定"的？（答不出就先写，写完再对答案）
//     ② 类上要有能被 Spring 扫到、且**默认单例**的注解
//        —— 想清楚：跨轮记住提醒列表，靠的是什么？
//     ③ 用一个字段把提醒存起来（内存即可）
//
//   ⚠️ 别忘了：这个类的实例后面要交给 `.tools(...)` 用。
//
// 自检（写完自己打勾，别先看答案）：
//   [ ] 返回值类型是 Map（不是 String）
//   [ ] 有 @Tool 注解 + description（description 要写清"什么时候该调它"）
//   [ ] 类上有 @Component（或等价）
//   [ ] 状态字段是实例字段，不是 static
//   [ ] 方法名/参数名没有拼错（Java 编译器能帮你挡一半，但 description 里的字它不管）
// ══════════════════════════════════════════════════════════════════════

import com.laozhang.assistant.model.Reminder;
import org.springframework.ai.tool.annotation.Tool;
import org.springframework.ai.tool.annotation.ToolParam;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.context.annotation.RequestScope;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

@Component
public class AssistantTools {



    private static final DateTimeFormatter TIME_FORMATTER =
            DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final List<Reminder> reminders = new CopyOnWriteArrayList<>();


    @Tool(description = "添加一条提醒事项（仅登记到列表，不会到点自动提醒/弹窗，也不支持重复或周期提醒）。"
            + "当用户说'提醒我'、'记一下'、'别让我忘了'，或说'设个闹钟'、'加个备忘'、'存一下'时使用 —— "
            + "这类说法都走本工具（只是记一笔，不是真的定时响铃）。"
            + "参数 content 是要提醒的内容，when 是提醒时间（如'明天上午9点'，用户没说就填'未指定'）。")
    public Map<String, Object> addReminder(
            @ToolParam(description = "提醒的内容，例如：交周报") String content,
            @ToolParam(description = "提醒时间描述，例如：明天上午9点；用户没提时间就填'未指定'") String when) {
        Map<String, Object> resultMap = new HashMap<>();
        try {
            Reminder reminder = new Reminder();
            reminder.setContent(content);
            reminder.setWhen(when);
            reminders.add(reminder);
            resultMap.put("ok", true);
            resultMap.put("message", "已添加提醒：" + content + "（" + when + "），当前共 " + reminderCount() + " 条");
        } catch (Exception e) {
            resultMap.put("error", e.getMessage());
        }
        return resultMap;
    }

    @Tool(description = "计算一个算术表达式，支持加(+)、减(-)、乘(*)、除(/)和括号。"
            + "当用户问'等于多少'、'算一下'、涉及数字计算时使用。"
            + "参数 expression 是要计算的数学表达式，例如：(12+8)*3")
    public String calculate(@ToolParam(description = "数学表达式，只含数字和 + - * / ( ) . ，例如：(12+8)*3") String expression) {

        String reg = "[0-9+\\-*/().\\s]+";

        if (expression == null || !expression.matches(reg)) {
            return "表达式含非法字符，只支持数字和 + - * / ( )";
        }

        try {
            String result = String.valueOf(new SpelExpressionParser().parseExpression(expression).getValue());
            return expression + " = " + result;
        } catch (Exception e) {
            return "计算出错：" + e.getMessage();
        }
    }


    @Tool(description = "获取当前的日期和时间。当用户问'现在几点'、'今天几号'、'当前时间'时使用。无参数。")
    public String getCurrentTime() {
        // ⚠️ DateTimeFormatter 是**线程安全**的 → 做成 static final 常量，
        //    别每次调用都 ofPattern 一遍（和 Python 里预先编译正则 re.compile 是同一个道理）。
        //    格式串的大小写有语义（写错不一定报错，见下面注释）：
        //      yyyy 年 ｜ MM **月** ｜ dd 日 ｜ HH **24小时制**小时 ｜ mm **分钟** ｜ ss 秒
        return "现在是 " + LocalDateTime.now().format(TIME_FORMATTER);
    }


    public Integer reminderCount() {
        return reminders.size();
    }

}