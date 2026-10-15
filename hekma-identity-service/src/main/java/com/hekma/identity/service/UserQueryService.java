package com.hekma.identity.service;

import com.hekma.identity.domain.PatientDetailEntity;
import com.hekma.identity.domain.Role;
import com.hekma.identity.domain.UserEntity;
import com.hekma.identity.repository.PatientDetailRepository;
import com.hekma.identity.repository.UserRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
@Transactional(readOnly = true)
@Slf4j
public class UserQueryService {

    private final UserRepository userRepository;
    private final PatientDetailRepository patientDetailRepository;

    public UserQueryService(UserRepository userRepository, PatientDetailRepository patientDetailRepository) {
        this.userRepository = userRepository;
        this.patientDetailRepository = patientDetailRepository;
    }

    /**
     * Retrieve all users, or filter by role if provided.
     *
     * @param role optional role to filter by; if null, all platform users are returned
     * @return list of matching users ordered by creation date descending
     */
    public List<UserEntity> getUsers(Role role) {
        if (role == null) {
            log.info("Fetching all users across platform (all roles)");
            return userRepository.findAllByOrderByCreatedAtDesc();
        }
        log.info("Fetching users filtered by role: {}", role);
        return userRepository.findByRoleOrderByCreatedAtDesc(role);
    }

    /**
     * Retrieve user by database UUID.
     *
     * @param id the user UUID
     * @return optional user entity
     */
    public Optional<UserEntity> getUserById(UUID id) {
        return userRepository.findById(id);
    }

    /**
     * Retrieve user by email address.
     *
     * @param email user email
     * @return optional user entity
     */
    public Optional<UserEntity> getUserByEmail(String email) {
        if (email == null || email.trim().isEmpty()) {
            return Optional.empty();
        }
        return userRepository.findByEmail(email.trim().toLowerCase());
    }

    /**
     * Count users, optionally filtered by role.
     *
     * @param role optional role filter; if null, total count across all roles
     * @return count of matching users
     */
    public long getUserCount(Role role) {
        if (role == null) {
            return userRepository.count();
        }
        return userRepository.countByRole(role);
    }

    /**
     * Batch fetch patient details for a list of users to resolve GraphQL subfields efficiently.
     *
     * @param users list of user entities
     * @return map from UserEntity to PatientDetailEntity
     */
    public Map<UserEntity, PatientDetailEntity> getPatientDetailsForUsers(List<UserEntity> users) {
        if (users == null || users.isEmpty()) {
            return Collections.emptyMap();
        }

        List<UserEntity> patientUsers = users.stream()
                .filter(u -> u.getRole() == Role.PATIENT)
                .toList();

        if (patientUsers.isEmpty()) {
            return Collections.emptyMap();
        }

        List<PatientDetailEntity> details = patientDetailRepository.findByUserIn(patientUsers);
        return details.stream()
                .collect(Collectors.toMap(PatientDetailEntity::getUser, Function.identity(), (existing, replacing) -> existing));
    }

    /**
     * Get patient detail for a single user.
     *
     * @param user user entity
     * @return optional patient detail
     */
    public Optional<PatientDetailEntity> getPatientDetailForUser(UserEntity user) {
        if (user == null || user.getRole() != Role.PATIENT) {
            return Optional.empty();
        }
        return patientDetailRepository.findByUser(user);
    }
}
