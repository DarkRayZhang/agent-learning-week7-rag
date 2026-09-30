package com.laozhang.assistant;

import com.laozhang.assistant.tool.AssistantTools;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

// ══════════════════════════════════════════════════════════════════════
//  ★ 空白页测验 · 第二题：模型调用最小链路
// ══════════════════════════════════════════════════════════════════════
// 要求（闭卷）：
//
//   写一个 `AssistantApplication`：
//     ① `@SpringBootApplication` + `main`（调 `SpringApplication.run(...)`）
//     ② 一个 `CommandLineRunner`（或 `@Bean` 返回 CommandLineRunner），
//        里面用 **ChatClient** 发一句话：
//
//            提醒我明天上午9点交周报。
//
//     ③ 绑定上一题写的工具，取回文本回答并打印
//
//   ⚠️ 三个必须自己想清楚的点：
//     · `ChatClient` 怎么拿到？（别 `new`，它是框架给的）
//     · 工具怎么绑上去？（传**实例**还是 Class？）
//     · 怎么把回答取成字符串？
//
// 自检（写完自己打勾，别先看答案）：
//   [ ] `ChatClient` 是通过**注入/构建器**拿到的，不是 `new ChatClient()`
//   [ ] 工具绑的是**对象实例**，不是 `Class`
//   [ ] 拿到了 `.content()`（文本），不是整个 response 对象被 toString
//   [ ] `main` 只有一个，且 `@SpringBootApplication` 在**能被扫描到的包**里
// ══════════════════════════════════════════════════════════════════════
@SpringBootApplication
public class AssistantApplication {

    public static void main(String[] args) {
        SpringApplication.run(AssistantApplication.class, args);
    }



    @Bean
    public CommandLineRunner chat(ChatClient.Builder builder, AssistantTools tools) {
        return args ->  {
            ChatClient chatClient = builder.build();
            String[] questions = new String[]{
                    "提醒我明天上午9点交周报。",
                    "再帮我记一条：后天下午3点开周会。",
                    "我的备忘里有没有关于发布值班的内容？"};
            for(String question : questions) {
                String content = chatClient.prompt().user(question).tools(AssistantTools.class).call().content();
                System.out.println("Q: " + question);
                System.out.println("A: " + content);
                System.out.println("────────────");
            }
        };
    }


}