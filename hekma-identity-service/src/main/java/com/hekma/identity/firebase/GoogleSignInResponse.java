package com.hekma.identity.firebase;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import lombok.Data;

@Data
@JsonIgnoreProperties(ignoreUnknown = true)
public class GoogleSignInResponse {
    private String idToken;
    private String email;
    private String refreshToken;
    private String expiresIn;
    private String localId;
    private Boolean registered;
}
