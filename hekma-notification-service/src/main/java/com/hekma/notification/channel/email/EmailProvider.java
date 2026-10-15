package com.hekma.notification.channel.email;

import com.hekma.notification.channel.NotificationResult;

public interface EmailProvider {
    NotificationResult sendEmail(String to, String subject, String body, String from);
}
