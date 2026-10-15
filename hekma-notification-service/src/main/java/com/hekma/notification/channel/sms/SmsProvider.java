package com.hekma.notification.channel.sms;

import com.hekma.notification.channel.NotificationResult;

public interface SmsProvider {
    NotificationResult sendSms(String phoneNumber, String message);
}
