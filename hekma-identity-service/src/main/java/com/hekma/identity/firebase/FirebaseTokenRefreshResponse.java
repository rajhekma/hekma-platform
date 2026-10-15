package com.hekma.identity.firebase;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class FirebaseTokenRefreshResponse {
    private String idToken;
    private String refreshToken;
    private String tokenType;
    private Long expiresIn;
    private String firebaseUid;
    private String projectId;
}
